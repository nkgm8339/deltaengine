# Coding Guideline

**Document ID**: IMP-001
**Version**: v3.0
**Status**: Draft

---

# 1. Purpose

Define implementation conventions for all source code produced from this Architecture Repository.

---

# 2. General Principles

- Readability over cleverness
- Single Responsibility Principle
- Dependency Injection where appropriate
- Configuration-driven behavior
- No duplicated business logic

---

# 3. Naming

| Element | Convention |
|---------|------------|
| Variables | snake_case |
| Functions | snake_case |
| Classes | PascalCase |
| Constants | UPPER_SNAKE_CASE |
| Modules | snake_case |

---

# 4. Error Handling

- Use standard Error Codes.
- Never suppress exceptions silently.
- Log all recoverable failures.

---

# 5. Logging

- UTC timestamps
- Structured logging
- Configurable log level

---

# 6. Testing

- Unit tests required
- Integration tests for module interfaces
- Deterministic replay supported

---

# 7. References

- Documentation_Standard_v3.0.md
- ErrorCodes_v3.0.md
- TestSpecification_v3.1.md