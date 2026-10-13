# Review Lenses

Go through every lens. A lens with nothing wrong produces no finding. Stay at the architecture level: components, flows, and the guarantees between them.

## Requirements fit
- Does each functional requirement have a flow that serves it?
- Does each non-functional requirement (latency, availability, durability, consistency) have a mechanism that meets it at the stated scale?
- What must always be true for the business (no double charge, no lost order), and which component guarantees it?

## Right-sizing
- Which component can be removed without breaking a requirement? Caches, queues, extra services and extra stores are the usual candidates.
- Which component exists for a scale the numbers do not reach?
- Is there a simpler shape that meets every requirement, such as fewer services or one store instead of two?
- Which component hits its limit first at peak, and is that limit within reach of the stated scale?

## Failure handling, as the proposer presented it
Skip this lens when the proposal has no failure section. Problems here go under what to change.
- For each failure the proposer listed: does the stated handling actually work?
- For each accepted downtime or degradation: how often can it happen, how long does it last, and does that fit the availability budget?
- Is the degradation acceptable to the user, for example read-only for 30 seconds compared with lost writes?

## Failures the proposer missed
These go under failures they missed. With no failure section, every failure that matters at this scale is a missed one.
- Is there a single component every request depends on, with no stated recovery?
- What happens when a dependency is slow rather than down?
- Can a write be lost, duplicated or left half-done across two components? What happens on retry?
- What is the blast radius: does one failure take down one feature or the whole system?

## Consistency
- Where is the source of truth for each piece of data?
- Where is the design eventually consistent, and can the user-visible behaviour tolerate it?

## Operability
- Can it be deployed and rolled back without breaking the availability target?
- How does someone know it is unhealthy before users do?
