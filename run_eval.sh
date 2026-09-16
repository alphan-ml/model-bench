#!/bin/bash
set -x
export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH
cd $HOME/Claude/model-bench
export AWS_REGION=us-east-1
export MODELBENCH_ADAPTER=bedrock
for m in nova llama mistral; do
  echo "=== START $m $(date -u) ==="
  .venv/bin/python -m modelbench.cli run --model $m
  echo "=== END $m $(date -u) exit=$? ==="
done
echo ALL_DONE
