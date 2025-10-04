from pathlib import Path
lines = Path("src/file_manager/file_manager.py").read_text(encoding="utf-8").splitlines()
for idx,line in enumerate(lines, start=1):
    if line.strip().startswith("class FileItemDelegate"):
        start=idx-1
        break
else:
    raise SystemExit('delegate not found')
for idx in range(start, len(lines)):
    if lines[idx].startswith('class ') and idx > start:
        end=idx
        break
else:
    end=len(lines)
print('\n'.join(lines[start:end]))
