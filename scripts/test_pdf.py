import fitz

doc = fitz.open("data/fta_us/18-06ROOs-1_kor.pdf")

all_text = ""

for page in doc:
    all_text += page.get_text()

with open("output/korus_psr.txt", "w", encoding="utf-8") as f:
    f.write(all_text)

print("완료")
print("총 글자수:", len(all_text))