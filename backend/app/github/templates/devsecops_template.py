# app/core/templates/devsecops_template.py

DEVSECOPS_TEMPLATE = """name: ZeroOps DevSecOps Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

permissions:
  contents: read
  security-events: write

jobs:
  audit-and-lint:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect Secrets (TruffleHog)
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
          extra_args: --only-verified

      - name: Setup Node.js Environment
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install Dependencies
        run: npm ci

  security-scans:
    needs: audit-and-lint
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Dependency Audit (SCA)
        run: npm audit --audit-level=high

      - name: Static Application Security Testing (SAST via Semgrep)
        uses: semgrep/semgrep-action@v1
        with:
          config: p/security-audit p/typescript p/node
"""