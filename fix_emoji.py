import re

with open("ApiInstructor.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove all non-ASCII emoji/symbols from print statements
# Match printable characters above U+2000 range (excluding ASCII letters)
lines = content.split("\n")
new_lines = []
for line in lines:
    if "print(" in line:
        # Replace common emoji/symbols in print lines
        line = line.replace("\u2705 ", "")   # ✅
        line = line.replace("\u274c ", "")   # ❌
        line = line.replace("\u2753 ", "")   # ❓
        line = line.replace("\u231b ", "")   # ⌛
        line = line.replace("\U0001f310 ", "")  # 🌐
        line = line.replace("\u26a0\ufe0f ", "")  # ⚠️
        line = line.replace("\u2139\ufe0f ", "")  # ℹ️
        line = line.replace("\U0001f504 ", "")  # 🔄
    new_lines.append(line)

content = "\n".join(new_lines)

with open("ApiInstructor.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed emoji in ApiInstructor.py")
