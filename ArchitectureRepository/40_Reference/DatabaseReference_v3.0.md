# DatabaseReference_v3.0

# Purpose

Defines the canonical database terminology and data storage principles
used throughout the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Database Concepts

  Term          Definition
  ------------- -----------------------------------------------------------
  Database      Structured storage system for persistent data management.
  Table         Logical collection of records with a defined schema.
  Record        Single stored data entry.
  Field         Individual attribute within a record.
  Primary Key   Unique identifier for each record.
  Foreign Key   Reference linking records between related tables.
  Index         Data structure improving query performance.
  Schema        Definition of database structure and relationships.

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for database terminology.
-   Architecture and Modules shall reference these definitions.
-   Database engine-specific features may extend but shall not redefine
    these concepts.

Status: Phase4 Reference Enhancement
