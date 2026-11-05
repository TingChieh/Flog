# Search Hardening Design

## Goal

Prevent anonymous search requests from loading every post, and make `%`, `_`,
and the escape character search as literal text.

## Design

The search route trims `q`, rejects queries longer than 200 characters, and
returns an empty result set for an absent or whitespace-only query. For a
non-empty query it uses SQLAlchemy's `contains(..., autoescape=True)`, orders
by newest post first, and paginates using the existing `POSTS_PER_PAGE`
setting. Pagination links preserve the literal query.

## Scope

The search still looks only in post bodies. No search-index dependency,
ranking system, or change to post visibility is introduced.

## Verification

Regression tests cover empty searches, literal SQL LIKE metacharacters,
pagination, and the maximum query length. Existing UI and post-view tests
remain green.
