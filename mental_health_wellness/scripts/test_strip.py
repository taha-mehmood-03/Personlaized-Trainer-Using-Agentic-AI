import sys, re
sys.stdout.reconfigure(encoding="utf-8")

def strip(text):
    text = re.sub(r"^\s*SELECTED_TECHNIQUE_ID\s*:\s*[^\s]+\s*(?:\r?\n)?", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r"^\s*[a-z0-9]{8,32}(?=\s)", "", text, count=1)
    return text.strip()

cases = [
    ("5fcd61er3ey  It makes so much sense...", "It makes so much sense"),
    ("SELECTED_TECHNIQUE_ID: abc123xyz\nReal response here.", "Real response here."),
    ("Certainly, I understand...", "Certainly, I understand"),
    ("It sounds like you are struggling...", "It sounds like you are struggling"),
    ("cm9abc123xyz  Hello there", "Hello there"),
]
all_ok = True
for inp, expected in cases:
    result = strip(inp)
    ok = expected in result
    if not ok:
        all_ok = False
    label = "OK  " if ok else "FAIL"
    print(f"[{label}] {inp[:45]!r}")
    print(f"       => {result[:55]!r}")

print()
print("All tests passed" if all_ok else "SOME TESTS FAILED")
