#!/usr/bin/env bash
set -euo pipefail

DURATION_SECONDS="${DURATION_SECONDS:-1800}"
POLL_SECONDS="${POLL_SECONDS:-10}"
MIN_NET_BP="${MIN_NET_BP:-5}"
SYMBOL_FILTER="${WATCH_SYMBOLS:-}"

echo "timestamp_utc,symbol,direction,bybit_bid,bybit_ask,hl_bid,hl_ask,gross_bp,est_net_bp,total_cost_bp"

end_time=$((SECONDS + DURATION_SECONDS))

while [ "$SECONDS" -lt "$end_time" ]; do
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  PYTHONPATH=/app python scripts/check_executable_quotes.py 2>/tmp/canary_quote_errors.log \
    | awk -F, -v ts="$ts" -v min_net="$MIN_NET_BP" -v symfilter="$SYMBOL_FILTER" '
      BEGIN { OFS="," }
      NR == 1 { next }
      $2 == "ERROR" { next }
      {
        ok = 1
        if (symfilter != "") {
          ok = 0
          n = split(symfilter, wanted, ",")
          for (i = 1; i <= n; i++) {
            if ($1 == wanted[i]) ok = 1
          }
        }

        if (ok && ($10 + 0) >= min_net) {
          print ts, $1, $8, $2, $3, $4, $5, $9, $10, $11
        }
      }
    '

  sleep "$POLL_SECONDS"
done
