# Memory Entry Best Practices

How to file memories in cortex-ai so they're actually findable later.

These are usage patterns, not hard rules — but following them dramatically improves recall quality, especially as your palace grows past a few hundred memories.

---

## 1. One distinct topic per entry

Don't bundle multiple unrelated facts/tasks/decisions into a single `cortex_add` call. Each distinct topic deserves its own entry.

❌ **Bad** — multi-topic mega-entry:

> *Single entry titled "tomorrow tasks":*
> *1. Research vendor X for Q2 roadmap*
> *2. Fix the auth bug in the login flow*
> *3. Send proposal to Acme*
> *4. Review Q1 metrics*
> *5. Schedule retro*

✅ **Good** — one entry per topic:

> *Five separate entries, each focused on a single topic*

**Why:** semantic search ranks based on overall similarity to the query. If a search for *"auth bug"* matches an entry that's mostly about Acme proposal + Q1 metrics + retro scheduling, the signal for the auth bug gets diluted and the entry ranks lower than it should.

---

## 2. Lead with primary keywords

The first ~200 characters of an entry carry the most weight in semantic search. Put your most distinctive terms at the top.

❌ **Bad** — keywords buried at the end:

> *"Notes from today's planning session: discussed scope, deadlines, blockers, and finally — research vendor X for the competitive landscape work."*

✅ **Good** — keywords up front:

> *"Vendor X competitive landscape research — for the Q2 roadmap. Notes from today's planning session: scope, deadlines, blockers."*

The first sentence answers "what is this entry about?" Subsequent sentences fill in detail.

---

## 3. Use wing and room deliberately

**Wings** are top-level project/topic domains. **Rooms** are aspects within a wing.

When filing a memory, pick wing/room with intent — they double as search filters later.

When searching for project-scoped content, filter:

```python
cortex_search(query="...", wing="my-project")
```

Filtering by wing dramatically improves precision when you know the project.

---

## 4. When in doubt, file separately

Two related but distinct facts? **Two entries.** Filing separately costs nothing; un-burying merged facts later costs a lot.

A useful heuristic: if a future search query for one of the facts wouldn't return both naturally, they shouldn't share an entry.

---

## 5. Update, don't append

Need to revise an existing memory because something changed?

- Use `cortex_kg_invalidate` to mark the old fact as stale
- Then `cortex_add` the new fact

Don't append corrections to existing entries — that leaves both versions in semantic search rankings, and the search has no way to know which is current.

---

## 6. Save the *why*, not just the *what*

The code/config/notes you're filing memory about already exist somewhere else. The memory's value is the **context** — why this decision was made, what tradeoff it resolved, what alternatives were considered.

❌ **Bad** — restates what's already in the code:

> *"We use Postgres for the user database."*

✅ **Good** — captures why:

> *"Picked Postgres over MongoDB for the user database — needed strong transactional guarantees for the billing flow, and the read patterns are uniformly relational. MongoDB was on the table for flexibility but the cost of inconsistency outweighed the schema flexibility win."*

The first version is grep-able from the code. The second version answers a question that no code can answer: *why?*

---

## 7. Imagine the future search

Before writing an entry, ask: **what would I search for to find this in three months?**

Then make sure those terms appear, prominently, in the first sentence of the entry.

If you can't think of a search query that would surface the entry naturally, you probably haven't framed it well — or it doesn't deserve to be a memory.
