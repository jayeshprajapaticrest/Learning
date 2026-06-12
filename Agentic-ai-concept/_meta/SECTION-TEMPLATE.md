# Section template (the 12-part contract)

Every numbered section conforms to this structure so the reader always knows where to find a thing.
Copy this skeleton when authoring a new section. Not every subsection applies to every topic — omit
with a one-line "N/A because…" rather than leaving a confusing gap.

---

```markdown
# NN — <Section Title>

> One-sentence statement of what this section makes you able to do.

**Prerequisites:** <links to sections you should read first>
**You will be able to:** <3–5 concrete capabilities>

## 1. TL;DR (the 60-second version)
Bullet the 5–8 load-bearing facts. A reader skimming only this should not be *wrong*, just *shallow*.

## 2. Concepts at three altitudes
### 🟢 Beginner — the mental model
### 🟡 Intermediate — how it actually works
### 🔴 Expert — the trade-off surface

## 3. Architecture & diagrams
At least one Mermaid diagram. Show data flow, control flow, and the failure boundaries.

## 4. Real examples
Concrete, named, production-shaped scenarios (not "imagine an agent that…").

## 5. Code (production-grade, Python)
Type-hinted, Pydantic contracts, error handling shown. No toy snippets that ignore failure.

## 6. Design patterns
The canonical patterns, when each applies, and the forces that select between them.

## 7. Anti-patterns  ❌ → ✅
Each anti-pattern paired with the correction and *why* it bites.

## 8. Common failures & troubleshooting
Symptom → root cause → detection signal → resolution. Real, not hypothetical.

## 9. The four implication lenses
Every nontrivial decision is examined through:
- **Performance** (latency, throughput)
- **Security** (attack surface, blast radius)
- **Scalability** (what breaks at 100×)
- **Cost** (tokens, infra, human)

## 10. Decision framework
A matrix or flowchart: "use X when…, prefer Y when…, never Z if…".

## 11. Enterprise recommendations
The defensible default for a regulated, multi-team, high-scale org.

## 12. Interview-level questions
Staff/principal-grade questions *with* model answers or answer sketches.

---
### Sources
Primary sources, dated. `[Established] / [Emerging] / [Contested]` tags where relevant.
```

---

## Authoring rules

1. **No hallucinated specifics.** If a number rots (price, context length), teach how to look it up
   instead of hard-coding a value that will be wrong in three months.
2. **Separate fact from forecast.** Tag `[Established]`, `[Emerging]`, `[Contested]`.
3. **Senior audience.** Don't explain what a queue or a p99 is. Do explain what a "trajectory" or
   "context rot" is.
4. **Every claim is falsifiable or cited.** Prefer "Anthropic's guidance is X because Y" over "best
   practice is X."
5. **Cross-link, don't duplicate.** One canonical explanation per concept; everyone else links to it.
   Term definitions live in [GLOSSARY.md](GLOSSARY.md).
6. **Diagrams must add information**, not restate prose. If a diagram could be a sentence, cut it.
