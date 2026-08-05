"""R1 encoding verification: BOM and mojibake scan on Phase 9A text paths."""
import pathlib

FILES = [
    "CHANGELOG.md", "README.md", "README.zh-CN.md", "SUPPORT_MATRIX.md",
    "docs/CAPABILITY_ADMISSION.md", "docs/LOCAL_ASR.md", "docs/ROADMAP.md",
    "tests/security/test_speech_security_boundary.py",
    "tests/unit/test_speech_adapter.py", "tests/unit/test_speech_policy.py",
    "tests/unit/test_speech_service.py",
]

ok = True
for p in FILES:
    raw = pathlib.Path(p).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="replace")
    moji = ("\u9494" in text) or ("\ufffd" in text)
    status = "OK  " if (not bom and not moji) else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"{status} bom={bom} moji={moji} {p}")
print("ENCODING_CLEAN" if ok else "ENCODING_FAIL")
