# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

StructIQ is an AI-powered structural engineering assistant. This repository
holds the code. Design documents are on Google Drive at
`G:\My Drive\04-Systems Development\06-StructIQ\docs` (tech stack, folder
plan, six-layer diagram).

## Where things live

- Code: this repository (`src/structiq`, `tests`, `.claude`, `apps`).
- Codes and standards: `G:\My Drive\02-Engineering Knowledge\00-Reference Library`.
  Never copy them into this repository; read them through `config/paths.yaml`.
- Client project data: `G:\My Drive\01-Projects`. Never commit it.
- Deep recursive scans of `G:\My Drive` are slow and can time out; target
  specific folders.

## Engineering rules (draft, to be completed by the owner)

- Every output is a draft for review by a qualified engineer. Never present a
  result as approved or final.
- State the design code, clause and edition behind every check. If the clause
  is not available in the reference library, say so; do not quote from memory.
- Carry units on every quantity (Pint). No bare numbers in calculations.
- Validate inputs with Pydantic models before calculating.
- Every calculation function has a Pytest case checked against a hand
  calculation or a published worked example.
- Flag assumptions explicitly, and stop to ask when a required input is missing.

## Conventions

- Python 3.11+, `src` layout, package name `structiq`.
- Run tests with `pytest`.
- ETABS, SAFE, AutoCAD and Revit adapters run only on a Windows desktop with
  the software installed; keep them in `src/structiq/tools` behind interfaces
  so the calculation core stays testable without them.
