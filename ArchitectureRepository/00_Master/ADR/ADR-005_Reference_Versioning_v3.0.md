# ADR-005 — Reference Versioning

**Status**: Accepted  
**Version**: v3.0

---

# Context

References sections across the repository pin exact versioned filenames (e.g., `ErrorCodes_v3.0.md`). When a document is revised, every referencing document holds a stale reference. Under the repository rule that existing files shall not be edited, fixing stale references requires re-issuing every referencing document, which cascades indefinitely.

---

# Decision

References sections, and document mentions in body text, shall cite documents by **base name without version suffix** (e.g., `- ErrorCodes`, "per MarketDataSchema").

- The authoritative version of each document is determined by its filename and header in the repository, and by the CHANGELOG.
- Existing version-pinned references are NOT corrected retroactively; they are converted to base-name form when the containing document is next revised for other reasons.
- ADR identifiers (ADR-000 …) remain unchanged; only the version suffix is omitted (e.g., `- ADR-002_Module_Communication`).

---

# Rationale

- Eliminates reference-update cascades permanently.
- Preserves the no-edit rule for existing files.
- Version history remains traceable via document headers and CHANGELOG.

---

# Consequences

Positive

- Document revisions no longer force changes in referencing documents.

Trade-offs

- References no longer state which version was current at writing time; the CHANGELOG provides that history.
- Mixed styles (pinned / base-name) coexist until documents are naturally revised.

---

# Related Documents

- Documentation_Standard
- CHANGELOG.md
- ADR-001_Documentation_First
