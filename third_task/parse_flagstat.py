import sys
import re

with open(sys.argv[1]) as f:
    for line in f:
        if "mapped (" in line:
            # ожидается строка вида: "574794 + 0 mapped (92.47% : N/A)"
            match = re.search(r'\((\d+\.?\d*)%', line)
            if match:
                print(match.group(1))
                sys.exit(0)
print("0")
