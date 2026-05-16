# Copilot Personal Local Instructions

## Response Format
- Every response must end with `miao!` as the last line.

## Environment
- Always activate the project environment before running any code: `conda activate lckg`
- If the environment `lckg` is missing a package, suggest the install command (`conda install`) rather than switching environments.
- Do not use the base environment or any other environment unless explicitly instructed.

## Code Style & Comments
- When creating a new script or writing into an empty file, add a bilingual header comment (English + Chinese) at the top describing the script's purpose.
- Use Chinese when writing inline comments and docstrings, unless otherwise specified.

## Command-Line Arguments
- When writing scripts, all inputs, outputs, and configurable rules/parameters must be exposed as command-line arguments (e.g., via `argparse` in Python), not hardcoded.
- Every argument's `help` string must be written in Chinese.
- Every script must support `-h` / `--help` to print Chinese help information (this is provided automatically by `argparse` when all `help=` strings are in Chinese).
- Example argument style:
  ```python
  parser = argparse.ArgumentParser(description="脚本功能的中文描述")
  parser.add_argument("--input",  "-i", required=True, help="输入文件路径")
  parser.add_argument("--output", "-o", required=True, help="输出文件路径")
  parser.add_argument("--threshold", "-t", type=float, default=0.5, help="过滤阈值（默认：0.5）")
  ```
