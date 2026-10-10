"""
The document text the extraction model is served, rebuilt in Python.

A port of backend/internal/service/pdf_extractor.go in scalejade/perjanjian-baku-bi
(branch sys-prompt @ e028187). The app turns a PDF into the extraction model's
input like this, and nothing else touches the text in between:

    pdftotext -layout <pdf> -     ->  "\f" -> "\n"  ->  TrimSpace
    -> keepIndonesianOnly()       ->  "DOCUMENT:\n" + text

Training rows have to be built the same way. An adapter trained on text that
still carries the English half of a bilingual contract, or that is missing the
lines keepIndonesianOnly() drops, learns to map an input it is never served.

Kept deliberately literal -- same constants, same word lists, same order of
filters -- so a diff against the Go file stays readable. Two things Go and
Python disagree on are pinned explicitly rather than left to defaults:

  - RE2's \\s and \\S are ASCII ([\\t\\n\\f\\r ]); Python's are Unicode. The
    patterns below spell the ASCII classes out.
  - Go's len() counts bytes. The one ratio that depends on it
    (maxStrippedTextRatio) is computed on UTF-8 byte lengths here too.

If pdf_extractor.go changes, change this file in the same breath.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SOURCE = "scalejade/perjanjian-baku-bi@e028187 backend/internal/service/pdf_extractor.go"


class ExtractError(Exception):
    pass


# ------------------------------------------------------------ pdftotext

MINIMUM_VIABLE_TEXT_LENGTH = 100


def pdftotext_layout(pdf: Path) -> str:
    """extractWithPDFtotext: -layout, form feeds to newlines, trimmed."""
    try:
        out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                             capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise ExtractError("pdftotext not found — install poppler-utils")
    except subprocess.CalledProcessError as e:
        raise ExtractError(f"pdftotext failed on {pdf.name}: "
                           f"{e.stderr.decode('utf-8', 'replace')[:200]}")
    text = out.decode("utf-8", "replace").replace("\f", "\n").strip()
    if len(text.encode("utf-8")) < MINIMUM_VIABLE_TEXT_LENGTH:
        raise ExtractError(f"pdftotext output too short ({len(text)} chars)")
    return text


def served_document_text(pdf: Path) -> str:
    """ExtractTextFromPDF, primary path. The pdfminer fallback is not ported:
    it only runs when pdftotext fails, and a training document that needs it
    should be dropped, not trained on a second extractor's layout."""
    return keep_indonesian_only(pdftotext_layout(pdf))


# ------------------------------------------------ bilingual section split

_NOT_ALPHA = r"[^a-zA-Z\n]*"
_WS = r"[\t\n\f\r ]+"


def _line(body: str) -> re.Pattern:
    return re.compile(rf"^{_NOT_ALPHA}{body}{_NOT_ALPHA}$", re.I | re.M)


ENGLISH_SECTION_PATTERNS = [
    _line(rf"english{_WS}version"),
    _line(rf"english{_WS}translation"),
    _line(rf"in{_WS}the{_WS}english{_WS}language"),
    _line(rf"versi{_WS}bahasa{_WS}inggris"),
    _line(rf"terjemahan{_WS}(?:dalam{_WS})?bahasa{_WS}inggris"),
]

INDONESIAN_SECTION_PATTERNS = [
    _line(rf"versi{_WS}bahasa{_WS}indonesia"),
    _line(rf"dalam{_WS}bahasa{_WS}indonesia"),
    _line(rf"terjemahan{_WS}(?:dalam{_WS})?bahasa{_WS}indonesia"),
]


def _find_section_start(patterns: list[re.Pattern], text: str) -> int:
    first = -1
    for p in patterns:
        m = p.search(text)
        if m and (first < 0 or m.start() < first):
            first = m.start()
    return first


def filter_indonesian_content(text: str) -> str:
    eng = _find_section_start(ENGLISH_SECTION_PATTERNS, text)
    ind = _find_section_start(INDONESIAN_SECTION_PATTERNS, text)
    if eng < 0 and ind < 0:
        return text
    if eng >= 0 and ind < 0:
        indonesian = text[:eng].strip()
        return indonesian if indonesian else text
    if eng < 0 and ind >= 0:
        return text[ind:].strip()
    if ind < eng:
        return text[ind:eng].strip()
    return text[ind:].strip()


# ------------------------------------------------- language classification

AMBIGUOUS, INDONESIAN, ENGLISH = 0, 1, 2

INDONESIAN_STOPWORDS = {
    "yang", "dan", "atau", "akan", "adalah", "untuk", "dengan", "pada", "dari",
    "kepada", "dalam", "oleh", "sebagai", "apabila", "maka", "tersebut", "setiap",
    "bahwa", "tidak", "dapat", "telah", "sesuai", "berlaku", "kami", "anda",
}

ENGLISH_STOPWORDS = {
    "the", "and", "or", "will", "shall", "with", "for", "from", "this", "that",
    "under", "any", "have", "has", "if", "in", "on", "of", "to", "by",
    "we", "you", "your", "is", "are",
}

MIN_WORDS_FOR_CONFIDENT_LANGUAGE = 8
STOPWORD_RATIO_MARGIN = 2.0
_STOPWORD_TRIM = ".,;:()\"'“”‘’•/-"


def detect_language(text: str) -> int:
    words = text.split()
    if len(words) < MIN_WORDS_FOR_CONFIDENT_LANGUAGE:
        return AMBIGUOUS
    ind = eng = 0
    for w in words:
        c = w.strip(_STOPWORD_TRIM).lower()
        ind += c in INDONESIAN_STOPWORDS
        eng += c in ENGLISH_STOPWORDS
    if ind > 0 and ind >= eng * STOPWORD_RATIO_MARGIN:
        return INDONESIAN
    if eng > 0 and eng >= ind * STOPWORD_RATIO_MARGIN:
        return ENGLISH
    return AMBIGUOUS


def split_language_runs(text: str) -> list[tuple[list[str], int]]:
    runs: list[tuple[list[str], int]] = []
    for line in text.split("\n"):
        lang = detect_language(line) if line.strip() else AMBIGUOUS
        if not runs:
            runs.append(([line], lang))
            continue
        lines, cur = runs[-1]
        if lang == AMBIGUOUS or lang == cur:
            lines.append(line)
            continue
        runs.append(([line], lang))
    return runs


MAX_STRIPPED_TEXT_RATIO = 0.7


def strip_english_translations(text: str) -> str:
    runs = split_language_runs(text)
    if len(runs) < 2:
        return text
    kept: list[str] = []
    seen_indonesian = False
    stripped_bytes = total_bytes = stripped_runs = 0
    for lines, lang in runs:
        run_text = "\n".join(lines)
        n = len(run_text.encode("utf-8"))
        total_bytes += n
        if lang == ENGLISH and seen_indonesian:
            stripped_bytes += n
            stripped_runs += 1
            continue
        if lang == INDONESIAN:
            seen_indonesian = True
        kept.append(run_text)
    if stripped_runs == 0:
        return text
    if total_bytes > 0 and stripped_bytes / total_bytes > MAX_STRIPPED_TEXT_RATIO:
        return text
    return "\n".join(kept)


# ------------------------------------------------ inline bilingual headings

INDONESIAN_DOMAIN_WORDS = [
    "kartu", "kredit", "tagihan", "pembayaran", "pemegang", "nasabah", "rekening",
    "transaksi", "dana", "bunga", "denda", "biaya", "tarif", "iuran", "angsuran",
    "cicilan", "saldo", "jumlah", "nomor", "tanggal", "jatuh", "tempo", "bulan",
    "tahun", "hari", "minggu", "waktu", "masa", "layanan", "ketentuan", "syarat",
    "perjanjian", "konsumen", "penyelenggara", "pengguna", "pihak", "ketiga",
    "hukum", "pengadilan", "sengketa", "pengaduan", "keluhan", "permintaan",
    "persetujuan", "pemberitahuan", "perubahan", "penggunaan", "penggantian",
    "kehilangan", "kerusakan", "keamanan", "kerahasiaan", "pribadi", "jasa",
    "barang", "produk", "pasal", "ayat", "peraturan", "umum", "lain", "lainnya",
    "wajib", "harus", "berhak", "hak", "kewajiban", "tanggung", "jawab",
    "kerugian", "gugatan", "pelanggaran", "penyalahgunaan", "pelindungan",
    "perlindungan", "penarikan", "tunai", "uang", "belanja", "pembelanjaan",
    "pemakaian", "penerbit", "pengembalian", "pelunasan", "keterlambatan",
    "pemblokiran", "penutupan", "pembatalan", "pendaftaran", "penagihan",
    "tunggakan", "penjamin", "jaminan", "formulir", "lembar", "cetak", "salinan",
    "fotokopi", "bukti", "catatan", "keterangan", "penjelasan", "contoh",
    "ilustrasi", "perhitungan", "kualitas", "alamat", "telepon", "kantor",
    "cabang", "negara", "negeri", "luar", "nilai", "tukar", "kurs", "valuta",
    "asing", "fasilitas", "pengakhiran", "tata", "cara", "mekanisme", "prosedur",
    "seputar", "penting", "sementara", "kenaikan", "petunjuk", "nama", "batas",
    "pita", "magnetik", "tanda", "tangan", "definisi", "istilah", "pendahuluan",
    "penutup", "sanksi", "penyelesaian", "kepatuhan", "pengawasan", "pelaporan",
    "laporan", "kegagalan", "gangguan", "sistem", "elektronik", "rincian",
    "daftar", "ringkasan", "kepemilikan", "penyimpanan", "pemeliharaan",
    "pemutusan", "kerjasama", "pemrosesan", "pengiriman", "penerimaan",
    "pembukuan", "pemotongan", "penghentian", "ketersediaan",
    "atas", "juga", "serta", "karena", "jika", "bila", "saat", "seluruh", "semua",
    "antara", "tanpa", "melalui", "secara", "terhadap", "mengenai", "tentang",
    "sejak", "sampai", "hingga", "setelah", "sebelum", "selama",
]

INDONESIAN_VOCABULARY = INDONESIAN_STOPWORDS | set(INDONESIAN_DOMAIN_WORDS)

MAX_BILINGUAL_HEADING_CHARS = 120     # Go: bytes
MAX_ENGLISH_TRANSLATION_WORDS = 12

# Go: `^([^/]*\S)[ \t]*/[ \t]*([A-Z][^/]*?)[ \t]*$` -- \S spelled as RE2's ASCII class.
BILINGUAL_HEADING = re.compile(r"^([^/]*[^\t\n\f\r /])[ \t]*/[ \t]*([A-Z][^/]*?)[ \t]*$")
DIGIT = re.compile(r"[0-9]")
_WORD_TRIM = ".,;:()[]\"'“”‘’•/-"


def alphabetic_words(text: str) -> list[str]:
    out = []
    for field in text.split():
        w = field.strip(_WORD_TRIM).lower()
        if w and all(ch.isalpha() for ch in w):
            out.append(w)
    return out


def is_english_translation_of(indonesian: str, english: str) -> bool:
    if DIGIT.search(english):
        return False
    en = alphabetic_words(english)
    if not en or len(en) > MAX_ENGLISH_TRANSLATION_WORDS:
        return False
    if any(w in INDONESIAN_VOCABULARY for w in en):
        return False
    idn = alphabetic_words(indonesian)
    if idn == en:
        return True
    return any(w in INDONESIAN_VOCABULARY for w in idn)


def strip_inline_english_translation(line: str) -> str:
    if len(line.encode("utf-8")) > MAX_BILINGUAL_HEADING_CHARS:
        return line
    m = BILINGUAL_HEADING.match(line)
    if not m:
        return line
    indonesian, english = m.group(1), m.group(2)
    return indonesian if is_english_translation_of(indonesian, english) else line


def strip_inline_english_translations(text: str) -> str:
    return "\n".join(strip_inline_english_translation(l) for l in text.split("\n"))


# ------------------------------------------------------------------ entry

def keep_indonesian_only(text: str) -> str:
    return strip_english_translations(
        strip_inline_english_translations(filter_indonesian_content(text)))


def is_english_document(text: str) -> bool:
    """IsEnglishDocument: the app rejects these before extraction ever runs."""
    ind = eng = 0
    for lines, lang in split_language_runs(text):
        n = len("\n".join(lines).encode("utf-8"))
        if lang == INDONESIAN:
            ind += n
        elif lang == ENGLISH:
            eng += n
    if ind + eng == 0 or eng == 0:
        return False
    return ind / (ind + eng) < 0.10
