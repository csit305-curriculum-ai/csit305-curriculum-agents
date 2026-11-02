#!/usr/bin/env bash
# Fetch the raw curriculum source files into corpus/raw/ (not committed: redistribution licence unclear).
# The original moe.gov.ae URLs now return 404, so the Internet Archive copies are used. See corpus/SOURCES.md.
set -euo pipefail
cd "$(dirname "$0")/../corpus" && mkdir -p raw
UA="Mozilla/5.0 (research corpus fetch)"
MOE="www.moe.gov.ae/Ar/ImportantLinks/Assessment/Documents/Curriculum-docs"
fetch() { curl -sSL -m 120 -A "$UA" -o "raw/$1" "$2"; echo "fetched $1"; }
fetch moe_math_scope_sequence_g1-12.pdf "https://web.archive.org/web/2022id_/https://$MOE/Scope%20and%20Sequence%20_%20Math%20G1-12%20_%20Work_in_Progress.pdf"
fetch moe_science_framework_2019-20.pdf "https://web.archive.org/web/2022id_/https://$MOE/MOE%20Science%20Framework%202019-20.pdf"
fetch timss2023_uae_encyclopedia.pdf "https://timss2023.org/wp-content/uploads/2024/10/United-Arab-Emirates.pdf"
sha256sum raw/*.pdf
echo "Compare these hashes with corpus/SOURCES.md. A mismatch means the source changed: stop and record it."
