# User-Facing Documentation Corrections Design

## Purpose

Bring the README and its linked user guides in line with recently merged user-facing features.

## Audience and document types

- The README remains a concise product overview for prospective users and operators.
- The log and Deploy New Instance pages remain task-oriented how-to guides for QLSM operators.
- The Hooks page remains an explanation and operating guide for administrators using native hooks.

## Changes

- Expand the README log feature text to name the available filters.
- Add the MinQLX `damage` event to the README's plugin-management feature text.
- Document Last N Lines, Time Range, and All filtering on the Chat Logs page.
- Add the existing All mode to the Server Logs filter list.
- Document the Hooks tab in the pre-deployment workflow, including its preset-derived limitations.
- Explain on the Hooks page how hook selection and ordering work before an instance exists.

## Constraints

- Do not add the legacy service-enablement reconciliation warning.
- Do not change release or version metadata.
- Do not change application behavior or API documentation.

## Validation

Build the MkDocs user guide in strict mode and inspect the diff for accurate terminology, working links, and consistent Markdown.
