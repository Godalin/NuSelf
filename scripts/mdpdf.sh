#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/mdpdf.sh [-o OUTPUT_DIR] file1.md [file2.md ...]

Convert one or more Markdown files to PDF with pandoc + xelatex.

Options:
  -o, --output-dir DIR   Write PDFs into DIR instead of next to the source files.
  -h, --help             Show this help text.
EOF
}

output_dir=""
main_font="${PANDOC_MAIN_FONT:-Times New Roman}"
cjk_font="${PANDOC_CJK_MAIN_FONT:-Hiragino Sans GB}"
mono_font="${PANDOC_MONO_FONT:-Menlo}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: missing value for $1" >&2
        exit 1
      fi
      output_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 1
fi

if ! command -v pandoc >/dev/null 2>&1; then
  echo "Error: pandoc is required but not installed." >&2
  exit 1
fi

if ! command -v xelatex >/dev/null 2>&1; then
  echo "Error: xelatex is required but not installed." >&2
  exit 1
fi

if [[ -n "$output_dir" ]]; then
  mkdir -p "$output_dir"
fi

echo "Using main font: $main_font" >&2
echo "Using CJK font: $cjk_font" >&2

for input_path in "$@"; do
  if [[ ! -f "$input_path" ]]; then
    echo "Error: file not found: $input_path" >&2
    exit 1
  fi

  base_name="$(basename "$input_path" .md)"
  if [[ "$base_name" == "$(basename "$input_path")" ]]; then
    base_name="$(basename "$input_path")"
  fi

  if [[ -n "$output_dir" ]]; then
    output_path="$output_dir/$base_name.pdf"
  else
    output_path="${input_path%.*}.pdf"
  fi

  pandoc \
    --from=gfm \
    --to=pdf \
    --pdf-engine=xelatex \
    --metadata=lang=zh-CN \
    --variable=mainfont="$main_font" \
    --variable=CJKmainfont="$cjk_font" \
    --variable=monofont="$mono_font" \
    --output="$output_path" \
    "$input_path"

  echo "Wrote $output_path"
done