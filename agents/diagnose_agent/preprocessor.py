# preprocessor.py
import os
import re
import json
import logging
import unicodedata
from pathlib import Path
from typing import List, Optional, Iterator, Tuple, Dict
import pdfplumber
import uuid

# --- VNCORENLP (optional) -----------------------------------------------------
try:
    import py_vncorenlp
    _VNCORENLP_AVAILABLE = True
except Exception:
    _VNCORENLP_AVAILABLE = False

def _vn_assets_ready(save_dir: Path) -> bool:
    """Chỉ kiểm tra đủ cho word segmentation (wseg)."""
    jar_ok = any((save_dir / n).exists() for n in ["VnCoreNLP-1.2.jar", "VnCoreNLP-1.1.1.jar"])
    ws = save_dir / "models" / "wordsegmenter" / "wordsegmenter.rdr"
    return jar_ok and ws.exists()


class VnTextProcessor:
    """
    Singleton wrapper cho VnCoreNLP:
    - KHÔNG tự tải model.
    - Nếu thiếu tài nguyên hoặc init fail -> dùng DummyProcessor.
    """
    _instance = None

    def __init__(self, save_dir: str = "./models/vncorenlp", annotators: Optional[List[str]] = None):
        if VnTextProcessor._instance is not None:
            # tái sử dụng instance đã tạo
            self.processor = VnTextProcessor._instance
            return

        annotators = annotators or ["wseg"]
        save = Path(save_dir)
        logger = logging.getLogger(__name__)

        # Nếu py_vncorenlp chưa cài -> Dummy
        if not _VNCORENLP_AVAILABLE:
            logger.warning("py_vncorenlp chưa cài. Dùng DummyProcessor (whitespace).")
            self.processor = DummyProcessor()
            VnTextProcessor._instance = self.processor
            return

        # Chỉ kiểm tra tài nguyên sẵn có
        if not _vn_assets_ready(save):
            logger.warning("Thiếu tài nguyên VnCoreNLP tại '%s'. Dùng DummyProcessor.", save)
            self.processor = DummyProcessor()
            VnTextProcessor._instance = self.processor
            return

        # Thử khởi tạo VnCoreNLP
        try:
            self.processor = py_vncorenlp.VnCoreNLP(annotators=annotators, save_dir=str(save))
            VnTextProcessor._instance = self.processor
        except Exception as e:
            logger.warning("Khởi tạo VnCoreNLP thất bại (%s). Dùng DummyProcessor.", e)
            self.processor = DummyProcessor()
            VnTextProcessor._instance = self.processor

    def word_segment(self, text: str) -> List[str]:
        # Một số bản py_vncorenlp chỉ có annotate_text
        try:
            return self.processor.word_segment(text)
        except AttributeError:
            try:
                out = self.processor.annotate_text(text)  # type: ignore[attr-defined]
                toks: List[str] = []
                for _, words in out.items():
                    if isinstance(words, list):
                        toks.extend([w.get("wordForm", "") for w in words if isinstance(w, dict)])
                return [t for t in toks if t]
            except Exception:
                return text.split()


class DummyProcessor:
    """Fallback đơn giản: tách theo khoảng trắng."""
    def word_segment(self, text: str) -> List[str]:
        return text.split()


# --- PREPROCESSOR -------------------------------------------------------------
class DataPreprocessor:
    """
    Tải và Tiền xử lý Tài liệu
    - Sử dụng thư viện pdfplumber (extract_words để giảm dính chữ)
    - Chuẩn hóa NFC
    - Loại bỏ khoảng trắng thừa (line-wise)
    - Lowercase
    - Repeated newline (gộp nhiều newline liên tiếp thành 1)
    - KHÔNG bỏ stopword
    Chunk = 1 trang, NO overlap.

    Tuỳ chọn: tích hợp VnCoreNLP để tạo thêm trường 'text_ws' (word-segmented).
    """

    def __init__(self,
                 in_dir: Path | str = "data/raw_pdfs",
                 out_jsonl: Path | str = "data/chunks.jsonl",
                 log_path: Path | str = "data/preprocess.log",
                 use_vncorenlp: bool = False,
                 vncorenlp_dir: Path | str = "models/vncorenlp") -> None:

        # Chuẩn hoá đường dẫn theo gốc project (file này nằm trong a2a_medical/)
        self.BASE_DIR = Path(__file__).resolve().parent.parent
        self.in_dir = Path(in_dir) if Path(in_dir).is_absolute() else self.BASE_DIR / in_dir
        self.out_jsonl = Path(out_jsonl) if Path(out_jsonl).is_absolute() else self.BASE_DIR / out_jsonl
        self.log_path = Path(log_path) if Path(log_path).is_absolute() else self.BASE_DIR / log_path
        self.vncorenlp_dir = Path(vncorenlp_dir) if Path(vncorenlp_dir).is_absolute() else self.BASE_DIR / vncorenlp_dir

        # Tạo thư mục cần thiết
        self.in_dir.mkdir(parents=True, exist_ok=True)
        self.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        #self.vncorenlp_dir.mkdir(parents=True, exist_ok=True)

        # Logging (file + console)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(self.log_path, encoding="utf-8"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        # VnCoreNLP (optional)
        self.use_vncorenlp = use_vncorenlp
        self.vnsegmenter = None
        if self.use_vncorenlp:
            if not _VNCORENLP_AVAILABLE:
                self.logger.warning("py_vncorenlp chưa được cài. Bỏ qua word-seg.")
            else:
                self.vnsegmenter = VnTextProcessor(save_dir=str(self.vncorenlp_dir), annotators=["wseg"])
                if isinstance(self.vnsegmenter.processor, DummyProcessor):
                    self.logger.warning("WSeg: dùng DummyProcessor (thiếu model hoặc init thất bại).")
                else:
                    self.logger.info("VnCoreNLP sẵn sàng (wseg).")

    # ---------------- PDF extraction ----------------
    def extract_pdf_pages(self, pdf_path: Path) -> Iterator[Tuple[int, str]]:
        """
        Chiến lược 0: extract_text (pdfminer)  → sạch dấu/spacing
        Chiến lược 1: word-level               → đẹp dòng
        Chiến lược 2: char-level combining-safe→ chống kẹo chữ
        """
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    page = page.dedupe_chars()
                except Exception:
                    pass

                # 0) pdfminer trước
                try:
                    txt0 = page.extract_text(x_tolerance=1.5, y_tolerance=3.0)
                except Exception:
                    txt0 = None
                if txt0 and txt0.strip():
                    yield i, txt0
                    continue

                # 1) word-level
                try:
                    words = page.extract_words(
                        x_tolerance=2.0,
                        y_tolerance=3.0,
                        use_text_flow=True,
                        keep_blank_chars=False
                    )
                except Exception:
                    words = []

                if words:
                    line_tol = 2.0
                    lines_map: Dict[int, List[dict]] = {}
                    for w in words:
                        key = round(w.get("top", 0) / line_tol)
                        lines_map.setdefault(key, []).append(w)

                    text_lines: List[str] = []
                    for key in sorted(lines_map.keys()):
                        line_words = sorted(lines_map[key], key=lambda w: w.get("x0", 0))
                        text_lines.append(" ".join(w.get("text", "") for w in line_words))
                    yield i, "\n".join(text_lines)
                    continue

                # 2) char-level fallback (combining-safe)
                chars = page.chars or []
                if not chars:
                    yield i, ""
                    continue

                line_tol = 2.0
                lines: Dict[int, List[dict]] = {}
                for ch in chars:
                    key = round(ch.get("top", 0) / line_tol)
                    lines.setdefault(key, []).append(ch)

                page_text: List[str] = []
                GAP = 1.0  # tăng lên 1.2 nếu vẫn dính

                for key in sorted(lines.keys()):
                    line_chars = sorted(lines[key], key=lambda c: c.get("x0", 0))
                    out: List[str] = []
                    prev = None

                    for ch in line_chars:
                        c = ch.get("text", "")
                        if not c:
                            prev = ch
                            continue

                        # khoảng trống ngang
                        dx = 0.0
                        if prev is not None:
                            dx = ch.get("x0", 0) - prev.get("x1", 0)
                            if dx < 0:  # nhiễu toạ độ
                                dx = 0.0

                        # tránh chèn space giữa base letter và combining mark
                        is_comb = unicodedata.combining(c) != 0
                        prev_char = prev.get("text", "") if prev is not None else ""
                        prev_is_comb = bool(prev_char) and unicodedata.combining(prev_char) != 0

                        # không space trước dấu đóng, không space sau dấu mở
                        no_space_before = c in ".,;:?!)]}»”’"
                        no_space_after_prev = prev_char in "([{«“‘"

                        if prev is not None:
                            if not (is_comb or prev_is_comb or no_space_before or no_space_after_prev):
                                if dx >= GAP:
                                    out.append(" ")

                        out.append(c)
                        prev = ch

                    page_text.append("".join(out))

                yield i, "\n".join(page_text)

    # ---------------- Text cleaning ----------------
    def _preprocess_text(self, raw: str) -> str:
        # Chuẩn hóa tiếng Việt
        t = unicodedata.normalize('NFC', raw or "")
        
        # Thay thế tab (\t) thành space
        t = t.replace('\t', ' ')
        
        # Giữ nguyên ký tự tiếng Việt, chỉ xóa ký tự đặc biệt không cần thiết
        t = re.sub(r'[^\w\sÀ-ỹ.,!?]', ' ', t)  
        
        # Xử lý hyphen (nối từ bị ngắt dòng)
        t = re.sub(r'-\s*\n\s*', '', t)
        
        # Xóa xuống dòng, khoảng trắng thừa
        t = re.sub(r'\n+', ' ', t)
        t = re.sub(r'\s+', ' ', t)
        
        # Xóa khoảng trắng trước dấu câu
        t = re.sub(r'\s([?.!,;:])', r'\1', t)

        # Xóa số trang (dài hơn 2 chữ số) hoặc số đứng 1 mình
        t = re.sub(r'\b\d{3,}\b', ' ', t)  
        
        # Xóa các chuỗi toàn số hoặc số đứng lẻ
        t = re.sub(r'\b\d+\b', '', t)

        # Xóa các ký tự/từ đơn lẻ (1 ký tự alphabets hoặc ký tự unicode tiếng Việt)
        t = re.sub(r'\b([A-Za-zÀ-ỹ])\b(?!\s*\.)', '', t)  # chỉ giữ lại chữ dài >1

        # Xóa khoảng trắng thừa
        t = re.sub(r'\s+', ' ', t).strip()

        # Xóa số index đầu dòng (1., 2., 3., 4, ...)
        t = re.sub(r'^\d+\.\s*|\b\d+\s', ' ', t)  
        
        # Xóa các từ như "CHƯƠNG", "Phần", "bảng" (bao gồm biến thể viết hoa/thường)
        t = re.sub(r'\b(CHƯƠNG|Phần|bảng|CHƯƠNG|PHẦN|BẢNG)\b', ' ', t, flags=re.IGNORECASE)
        
        # Strip lại lần cuối
        t = t.strip()
        return t

    # ---------------- Build ----------------
    def build(self) -> Path:
        total_files = total_pages = total_chunks = 0

        with open(self.out_jsonl, "w", encoding="utf-8") as fw:
            for fn in sorted(os.listdir(self.in_dir)):
                if not fn.lower().endswith(".pdf"):
                    continue
                total_files += 1
                pdf_path = self.in_dir / fn
                self.logger.info(f"Đang xử lý: {pdf_path.name}")

                try:
                    for page_no, raw in self.extract_pdf_pages(pdf_path):
                        total_pages += 1
                        text = self._preprocess_text(raw)
                        if not text:
                            self.logger.warning(f"Trang rỗng: {fn} p{page_no}")
                            continue

                        # Tạo ID ổn định từ (tên file, số trang) -> UUIDv5 (deterministic)
                        book_name = Path(fn).stem
                        cid = f"{fn}::p{page_no}"
                        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, cid))

                        rec = {
                            "id": point_id,       # <- ID hợp lệ cho Qdrant (UUID string)
                            "book_name": book_name,
                            "page": page_no,
                            "context": text       # <- văn bản đã preprocess

                        }

                        # Word-seg (nếu bật và có VnCoreNLP) -> thêm field text_ws
                        if self.use_vncorenlp and self.vnsegmenter is not None:
                            try:
                                ws_tokens = self.vnsegmenter.word_segment(text)
                                if isinstance(ws_tokens, list):
                                    if len(ws_tokens) and isinstance(ws_tokens[0], list):
                                        ws_flat = " ".join(tok for sent in ws_tokens for tok in sent)
                                    else:
                                        ws_flat = " ".join(ws_tokens)
                                else:
                                    ws_flat = str(ws_tokens)
                                rec["text_ws"] = ws_flat
                            except Exception as e:
                                self.logger.warning(f"WSeg lỗi tại {fn} p{page_no}: {e}")

                        fw.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        total_chunks += 1
                except Exception as e:
                    self.logger.error(f"Lỗi khi xử lý {fn}: {e}")

        self.logger.info(f"Hoàn tất: {total_files} file, {total_pages} trang, {total_chunks} chunk")
        return self.out_jsonl

# # ---------------- CLI ----------------
# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser(description="PDF → JSONL preprocessor (VN optional).")
#     parser.add_argument("--in_dir", type=str, default="data/raw_pdfs", help="Thư mục chứa PDF.")
#     parser.add_argument("--out", type=str, default="data/chunks.jsonl", help="Đường dẫn JSONL output.")
#     parser.add_argument("--log", type=str, default="data/preprocess.log", help="Đường dẫn file log.")
#     parser.add_argument("--wseg", action="store_true", help="Bật word segmentation với VnCoreNLP.")
#     parser.add_argument("--vn_dir", type=str, default="models/vncorenlp", help="Thư mục model VnCoreNLP.")

#     args = parser.parse_args()

#     dp = DataPreprocessor(
#         in_dir=args.in_dir,
#         out_jsonl=args.out,
#         log_path=args.log,
#         use_vncorenlp=args.wseg,
#         vncorenlp_dir=args.vn_dir,
#     )
#     out_path = dp.build()
#     print(f"✅ Done. Output: {out_path}")
