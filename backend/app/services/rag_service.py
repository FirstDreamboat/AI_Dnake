"""RAG 检索服务 - 基于 bge-m3 向量模型的高性能轻量实现

不依赖 chromadb 等重型向量库，采用「向量矩阵 + 倒排索引」两级索引：

- 向量检索：全部向量预构建为 L2 归一化 numpy 矩阵，检索时一次矩阵乘
  得到所有片段相似度，将 O(N) 逐条循环优化为向量化矩阵运算；
- 关键词检索：构建 token -> 片段倒排索引（按文档频率 DF 裁剪高频词控制内存），
  检索时只对命中候选精排，不再全量扫描；
- 混合检索（hybrid）：先取向量前 C 名与关键词命中并集作为候选，
  再对候选做向量+关键词加权融合精排，兼顾速度与召回质量。

向量与文本以 JSON 文件持久化（data/vector/vectors.json）：
{
  "chunks": [
    {"doc_id": 1, "chunk_id": 0, "text": "...", "embedding": [0.1, ...]},
    ...
  ]
}
"""
import json
import threading
from pathlib import Path

import numpy as np

from app.config import settings
from app.services.llm_service import llm_service

# 向量文件
VECTORS_FILE = "vectors.json"


class RAGService:
    """轻量向量检索服务"""

    def __init__(self):
        self._lock = threading.Lock()
        self._data_path: Path = settings.vector_db_path / VECTORS_FILE
        self._chunks: list[dict] = self._load()
        self._rebuild_index()

    # ---------- 持久化 ----------
    def _load(self) -> list[dict]:
        if self._data_path.exists():
            try:
                return json.loads(self._data_path.read_text(encoding="utf-8")).get("chunks", [])
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self) -> None:
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._data_path.write_text(
            json.dumps({"chunks": self._chunks}, ensure_ascii=False), encoding="utf-8"
        )

    # ---------- 分块 ----------
    def _chunk_text(self, text: str) -> list[str]:
        """结构化分块：优先按自然边界切分，保证单条用例/段落完整

        - 以工作表标题(###)、用例编号行、Markdown 标题、空行为边界
        - 过短行与相邻内容合并，超长行回退字符滑窗
        """
        size = settings.RAG_CHUNK_SIZE
        min_size = settings.RAG_CHUNK_MIN_SIZE
        chunks: list[str] = []
        buf = ""
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if len(line) > size:
                # 超长行：直接滑窗切分
                if buf:
                    chunks.append(buf)
                    buf = ""
                for i in range(0, len(line), size):
                    chunks.append(line[i : i + size])
                continue
            is_boundary = (
                line.startswith("###")
                or line.startswith("# ")
                or line.startswith("用例编号")
                or line.startswith("| 用例编号")
            )
            if is_boundary and buf:
                if len(buf) >= min_size:
                    chunks.append(buf)
                    buf = ""
                else:
                    # 当前块过短，与边界行合并
                    buf = f"{buf}\n{line}"
                    continue
            if buf and len(buf) + len(line) + 1 > size:
                chunks.append(buf)
                buf = ""
            buf = f"{buf}\n{line}" if buf else line
        if buf:
            chunks.append(buf)
        return chunks

    # ---------- 核心操作 ----------
    def index_document(self, doc, content: str) -> int:
        """将文档内容分块并向量化入库，返回块数量

        大文档分批生成向量（EMBED_BATCH_SIZE 条/批），单批失败不中断整体，
        收集错误后统一抛出，由上层记录失败原因。
        """
        chunks = self._chunk_text(content)
        if not chunks:
            return 0
        doc_id = doc.id
        batch_size = settings.EMBED_BATCH_SIZE
        max_chars = settings.EMBED_MAX_INPUT_CHARS
        new_chunks: list[dict] = []
        errors: list[str] = []
        pending: list[tuple[int, str]] = list(enumerate(chunks))
        while pending:
            batch = pending[:batch_size]
            pending = pending[batch_size:]
            # 单批字符量超限时从尾部裁剪（避免模型输入过长）
            used = 0
            batch_ok: list[tuple[int, str]] = []
            for idx, t in batch:
                if used + len(t) > max_chars:
                    room = max_chars - used
                    if room > 200:
                        batch_ok.append((idx, t[:room]))
                    break
                batch_ok.append((idx, t))
                used += len(t)
            if not batch_ok:
                continue
            try:
                embeddings = llm_service.embed([t for _, t in batch_ok])
            except Exception as e:  # noqa: BLE001 - 单批失败不中断整体
                errors.append(f"第 {batch_ok[0][0] + 1}-{batch_ok[-1][0] + 1} 块: {e}")
                continue
            if not embeddings:
                errors.append(f"第 {batch_ok[0][0] + 1}-{batch_ok[-1][0] + 1} 块: 模型返回空向量")
                continue
            for (idx, chunk_text), emb in zip(batch_ok, embeddings):
                if not emb:
                    continue
                new_chunks.append(
                    {
                        "doc_id": doc_id,
                        "chunk_id": idx,
                        "text": chunk_text,
                        "embedding": emb,
                        "product_line": getattr(doc, "product_line", None),
                    }
                )
        with self._lock:
            # 覆盖式重建该文档的向量（幂等）
            self._chunks = [c for c in self._chunks if c.get("doc_id") != doc_id]
            self._chunks.extend(new_chunks)
            self._save()
            self._rebuild_index()
        if errors:
            raise RuntimeError("；".join(errors[:3]) + ("…" if len(errors) > 3 else ""))
        return len(chunks)

    # ---------- 关键词检索（混合检索） ----------
    _STOP_WORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
        "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "is", "are",
    }

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """轻量分词：英文/数字按词切分，中文按单字+相邻二元组切分"""
        tokens: list[str] = []
        import re

        # 英文单词与数字
        for w in re.findall(r"[a-zA-Z0-9]+", text.lower()):
            if w not in RAGService._STOP_WORDS:
                tokens.append(w)
        # 中文字符（单字 + 二元组）
        zh = re.sub(r"[^\u4e00-\u9fff]", "", text)
        tokens.extend(zh)
        for i in range(len(zh) - 1):
            tokens.append(zh[i : i + 2])
        return tokens

    def _keyword_score(self, query: str, text: str) -> float:
        """计算查询与文本的关键词匹配分数（0~1），基于词频加权"""
        if not query or not text:
            return 0.0
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return 0.0
        from collections import Counter

        t_count = Counter(self._tokenize(text))
        if not t_count:
            return 0.0
        q_count = Counter(q_tokens)
        total = 0.0
        hit = 0.0
        for token, qf in q_count.items():
            tf = t_count.get(token, 0)
            total += qf
            if tf:
                # 词频越高的权重越大，但用平方根压缩避免长文本占优
                hit += qf * (1.0 + min(1.0, tf ** 0.5 - 1.0))
        return hit / total if total else 0.0

    # ---------- 内存索引（矩阵 + 倒排） ----------
    def _rebuild_index(self) -> None:
        """构建向量矩阵与倒排索引（写锁内调用，原子替换）

        1. 向量矩阵：全部向量按众数维度对齐、逐行 L2 归一化，检索时一次矩阵乘；
           非众数维度片段（异常数据）不参与向量检索，但保留在倒排索引中。
        2. 倒排索引：token -> 片段下标列表，按文档频率(DF)裁剪高频词控制内存。
        """
        # 1. 向量矩阵
        dim_counter: dict[int, int] = {}
        for c in self._chunks:
            emb = c.get("embedding")
            if emb:
                dim_counter[len(emb)] = dim_counter.get(len(emb), 0) + 1
        if not dim_counter:
            self._matrix: np.ndarray | None = None
            self._vec_rows: list[int] = []
        else:
            dim = max(dim_counter, key=dim_counter.get)
            rows: list[int] = []
            mat: list[list[float]] = []
            for i, c in enumerate(self._chunks):
                emb = c.get("embedding")
                if emb and len(emb) == dim:
                    rows.append(i)
                    mat.append(emb)
            m = np.asarray(mat, dtype=np.float32)
            norms = np.linalg.norm(m, axis=1)
            self._matrix = m / (norms[:, None] + 1e-9)
            self._vec_rows = rows
        # 2. 倒排索引（DF 裁剪：出现于过多片段的词视为无区分度，剔除以控制内存）
        n = len(self._chunks)
        df: dict[str, int] = {}
        posting: dict[str, list[int]] = {}
        for i, c in enumerate(self._chunks):
            seen: set[str] = set()
            for t in self._tokenize(c.get("text", "")):
                if t in seen:
                    continue
                seen.add(t)
                lst = posting.get(t)
                if lst is None:
                    posting[t] = [i]
                else:
                    lst.append(i)
                df[t] = df.get(t, 0) + 1
        cutoff = max(500, n // 10)
        self._inverted = {t: rows for t, rows in posting.items() if df[t] <= cutoff}

    def _keyword_candidates(
        self, query: str, limit: int = 5000, line_set: set[int] | None = None
    ) -> set[int]:
        """倒排索引粗筛：返回包含查询任一 token 的片段下标集合（去重）

        :param line_set: 产品线限定（chunk 下标集合），命中后与产品线求交集
        """
        cand: set[int] = set()
        for token in self._tokenize(query):
            rows = self._inverted.get(token)
            if not rows:
                continue
            cand.update(rows)
            if len(cand) >= limit:
                break
        if line_set is not None:
            cand &= line_set
        return cand

    def _chunk_out(self, idx: int, score: float) -> dict:
        chunk = self._chunks[idx]
        return {
            "doc_id": chunk.get("doc_id"),
            "chunk_id": chunk.get("chunk_id"),
            "text": chunk.get("text", ""),
            "score": round(score, 4),
        }

    def _search_keyword(self, query: str, top_k: int, line_set: set[int] | None = None) -> list[dict]:
        """纯关键词检索：倒排命中集内精排；无命中时回退全量扫描（保底）"""
        cand = self._keyword_candidates(query, line_set=line_set)
        if not cand:
            # 查询词均为停用词/高频词（已被索引裁剪）时，回退全量扫描保证与旧逻辑一致
            cand = set(range(len(self._chunks)))
            if line_set is not None:
                cand &= line_set
        scored: list[tuple[float, int]] = []
        for idx in cand:
            s = self._keyword_score(query, self._chunks[idx].get("text", ""))
            if s <= 0:
                continue
            scored.append((s, idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._chunk_out(idx, score) for score, idx in scored[:top_k]]

    def _search_vector(self, scores: np.ndarray, top_k: int) -> list[dict]:
        """纯向量检索：矩阵乘结果降序取前 top_k（score<=0 即截断）"""
        results: list[dict] = []
        for pos in np.argsort(scores)[::-1]:
            s = float(scores[pos])
            if s <= 0:
                break
            results.append(self._chunk_out(self._vec_rows[pos], s))
            if len(results) >= top_k:
                break
        return results

    def _search_hybrid(
        self, query: str, scores: np.ndarray, top_k: int, line_set: set[int] | None = None
    ) -> list[dict]:
        """混合检索：向量前 C 名 ∪ 关键词命中 → 候选精排（0.7 向量 + 0.3 关键词）"""
        c = max(1000, top_k * 200)
        n_rows = scores.shape[0]
        cand_vec: set[int] = set()
        if n_rows > c:
            cand_vec.update(int(p) for p in np.argpartition(scores, -c)[-c:])
        else:
            cand_vec.update(range(n_rows))
        vec_of = {self._vec_rows[p]: float(scores[p]) for p in cand_vec}
        cand = self._keyword_candidates(query, line_set=line_set) | set(vec_of)
        if line_set is not None:
            cand &= line_set
        scored: list[tuple[float, int]] = []
        for idx in cand:
            vs = vec_of.get(idx, 0.0)
            kw = self._keyword_score(query, self._chunks[idx].get("text", ""))
            vec_norm = (vs + 1.0) / 2.0
            score = 0.7 * vec_norm + 0.3 * kw
            if score <= 0:
                continue
            scored.append((score, idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._chunk_out(idx, score) for score, idx in scored[:top_k]]

    def _line_set(self, product_line: str | None) -> set[int] | None:
        """返回指定产品线对应的 chunk 下标集合；product_line 为空/未知时返回 None（不过滤）"""
        if not product_line:
            return None
        return {
            i for i, c in enumerate(self._chunks) if c.get("product_line") == product_line
        }

    def search(
        self,
        query: str,
        top_k: int | None = None,
        mode: str = "hybrid",
        product_line: str | None = None,
    ) -> list[dict]:
        """检索（FR-4.3 混合检索策略），返回 [{doc_id, chunk_id, text, score}]

        :param mode: hybrid（向量+关键词加权融合）/ vector（纯语义）/ keyword（纯关键词）
        :param product_line: 产品线过滤（intercom/smart_home/hospital），None/空=全库检索
        """
        top_k = top_k or settings.RAG_TOP_K
        if not self._chunks:
            return []
        line_set = self._line_set(product_line)
        if mode == "keyword":
            return self._search_keyword(query, top_k, line_set)
        # vector / hybrid：向量不可用（embedding 失败或库为空）时降级为纯关键词检索
        query_vec = llm_service.embed([query])
        q = np.asarray(query_vec[0], dtype=np.float32) if (query_vec and query_vec[0]) else None
        if q is None or self._matrix is None or self._matrix.shape[0] == 0:
            return self._search_keyword(query, top_k, line_set)
        q_unit = q / (np.linalg.norm(q) + 1e-9)
        scores = self._matrix @ q_unit  # (M,) 矩阵行已预归一化
        if line_set is not None:
            # 非产品线矩阵行分数置为 -inf，使其不进任何 top 截断
            mask = np.zeros(scores.shape[0], dtype=bool)
            for pos, chunk_idx in enumerate(self._vec_rows):
                if chunk_idx in line_set:
                    mask[pos] = True
            scores = np.where(mask, scores, -np.inf)
        if mode == "vector":
            return self._search_vector(scores, top_k)
        return self._search_hybrid(query, scores, top_k, line_set)

    def build_context(self, query: str, top_k: int | None = None) -> str:
        """检索并拼接为上下文文本，供用例生成参考"""
        hits = self.search(query, top_k)
        if not hits:
            return ""
        parts = [f"【参考知识 {i + 1}】{h['text']}" for i, h in enumerate(hits)]
        return "\n\n".join(parts)

    def delete_document(self, doc_id: int) -> None:
        """删除某文档的全部向量"""
        with self._lock:
            self._chunks = [c for c in self._chunks if c.get("doc_id") != doc_id]
            self._save()
            self._rebuild_index()

    def stats(self) -> dict:
        """向量库统计"""
        doc_ids = sorted({c.get("doc_id") for c in self._chunks})
        dims = sorted({len(c.get("embedding", [])) for c in self._chunks if c.get("embedding")})
        return {
            "chunk_count": len(self._chunks),
            "doc_count": len(doc_ids),
            "dimensions": dims,
        }


rag_service = RAGService()