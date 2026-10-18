# Initial HLD Discussion

A transcript of the session in which the HLD ([`docs/hld.md`](../docs/hld.md)) was produced from a hand-drawn Excalidraw flow, converted to Mermaid with `utilities/excalidraw2mermaid.py`. The flow file itself is not committed. The user's messages are verbatim. Claude's replies are verbatim; its tool calls (reading files, writing the doc) are summarized in italics.

---

## 1. The ask

**User:**

> i am trying to solve the following system design problem and the .md file i provide to you has the details on how the flow in my mind works, lets come up with a HLD document for this problem statement and the solution of it
>
> this is the flow: ticket-validation-system/references/ticket-validation.md
>
> The Problem Statement
> Design the ticket assignment, validation and activation system for a city's
> public transport: 50 subway stations and 30 bus routes, handling around
> 2 million trips a day.
>
> Ticket purchase and payment already exist. Tickets are bought at stations and
> assigned to a travel card. Riders validate or activate their ticket by tapping
> the card at station turnstiles or on buses.
>
> The shortest ticket is valid for `x` minutes from activation; riders can also
> buy day, week or month passes. The travel card stores no data; it only
> identifies itself. A card can have only one active ticket at a time.

*Claude read the flow file (two Mermaid diagrams, assignment and validation/activation, plus the user's notes on estimates, NFRs and the offline Bus 1 / Bus 2 conflict) and the repo's rulebook for how design docs are written, then wrote `docs/hld.md`.*

**Claude:**

> I've written the HLD at `ticket-validation-system/docs/hld.md`. It follows your flow and stays short enough to skim. I haven't committed it. Under the repo rules it belongs on a local `ticket-validation-system` branch, which I can create when you want to commit.
>
> **What it covers:** the problem, requirements (your five NFRs), your estimates, one combined architecture diagram, 7 key decisions with their trade-offs, keys, invariants, the assignment, tap and offline-sync flows (your Bus 1 / Bus 2 example as a sequence diagram), guarantees, failure modes and open questions.
>
> **Gaps I filled in your flow:**
> - **How conflicting activations are merged:** the earliest activation wins (`activated_at = min(current, incoming)`). Every activation event gets an `event_id` so central applies it only once. Together these mean events can arrive in any order or twice and every copy still ends up the same.
> - **What the status queue sends:** the card's full current state, not just the change. It's a log that each station or bus reads from its own position, so a bus can catch up after being offline. A bus offline longer than the log keeps messages, or a new bus, starts from a full copy taken from central.
> - **When the gate opens:** only after the activation and its outbox entry are saved to local disk. This is what makes NFR5 (no lost activations) hold.
> - **Clocks:** "earliest wins" only works if clocks on buses and stations stay synced, so that's listed as an invariant.
> - **Stale buses:** an offline bus can't see activations made elsewhere, so it can let through a ticket that has already expired. I've written this up as an accepted risk: the loss is limited to the offline window, and a valid rider is never wrongly rejected.
>
> **One change from your design:** I replaced the 3 central DB replicas with one primary plus one standby. At about 23 writes/s, read replicas add nothing, and the standby only exists to cut ticket-sales downtime when the primary fails. Tell me if you want the 3 replicas back.
>
> **Open questions for you (in the doc):**
> 1. Each station's local server is a single point of failure for that station. NFR3 only covers central being down. Options are a second server per station or letting gates fall back to central.
> 2. Do day, week and month passes run from activation (what I assumed) or by calendar day, week and month?
> 3. With one ticket per card, a ticket that is never used blocks the card from new purchases forever. My default is that an unused ticket expires N days after assignment.
> 4. Is "one ticket per card at a time" really what you want? It stops riders from buying next month's pass early.
> 5. Should a gate reject a second tap of the same card within a few seconds, so one ticket can't let two people through?

---

## 2. Pushback and answers

**User:**

> i have some questions and suggestions regarding the choices:
> - conflicitng activations: we should keep the latest_activated_at if the requests arrive lets say `y` minutes apart(10/5) so that the users have a good experience
> - clocks: should we keep the clock refresh on the buses part of the design, as the busses can go inactive and there might be clock skews
>
> now the open questions:
> 1. this is an accepted risk, document it as an accepted risk, we assume they are connected by lan physically and only go down on routine maintenance(clock syncs become more important now)
> 2. its time from activations
> 3. this is a good point, the user has to activate the ticket within 1 calendar year
> 4. yes this is acceptable, as the users can buy the tickets at the station when it expires: its what the FRs state
> 5. yes there has to be a cooldown, but it also needs to depend on the location, if its the same location smaller cooldown, different locations longer cooldown

**Claude:**

> Two of your points need a decision before I edit, because as written they clash with other parts of the design. The other four are clear and I'll apply them as stated.

*Claude asked three multiple-choice questions.*

**Question 1, merge rule.** *Conflicting activations: how should the 'keep the latest' rule work? I'm reading 'y minutes apart' as the gap between the activation times, not when the events reach central (that depends on when a bus reconnects). One catch: merging events two at a time with a 'within y' test gives different answers depending on arrival order. Example with y=5: taps at 10:00, 10:04 and 10:08 end as 10:08 in one order and 10:04 in another. Comparing every tap against the earliest one fixes that.*

| Option | Description |
|---|---|
| Latest within y of earliest (Recommended) | Final activation = the latest tap no more than y minutes after the earliest tap. Taps further out are ignored. Same answer in any order, and a stale bus can stretch a ticket by at most y. Central and edges keep the short list of taps per ticket. |
| Always the latest | max(activated_at). Simple and order-independent, but a bus that missed an activation can stretch a ticket by its whole duration (a day pass by almost a day). |

**User's answer:** Latest within y of earliest.

**Question 2, value of y.** Options: 5 minutes (a stale bus barely stretches a single ticket) or 10 minutes (more forgiving for the rider, more revenue lost per conflict).

**User's answer:** 5 minutes.

**Question 3, cooldown.** *With a long cooldown across different locations, a legitimate transfer is rejected (enter station A at 10:00, catch a bus outside at 10:04). Passing a card back over a gate happens at the same location, so the same location usually gets the longer cooldown. Which do you want?*

| Option | Description |
|---|---|
| Same place long, elsewhere short (Recommended) | Same station or bus: e.g. 10 min (stops a card passed back to a friend). Different location: e.g. 2 min, below the fastest real transfer (stops two people using one card at once). |
| Same place short, elsewhere long | As first suggested: e.g. same 1 min, different 10 min. A transfer made inside the long cooldown is rejected. |

**User's answer (typed in, neither option):** short cooldown at all places.

**Claude:**

> Applying the answers: the merge keeps the latest tap within 5 minutes of the earliest, and there's one short cooldown everywhere. A cross-location cooldown means every accepted tap (validations too, not only activations) has to reach the other edges, so the activation queue becomes a tap queue.

*Claude rewrote `docs/hld.md`.*

**Claude:**

> I've updated `ticket-validation-system/docs/hld.md` with all your answers. It's still uncommitted.
>
> **What changed:**
> - **Conflicting activations:** the activation that counts is the latest tap within `y` = 5 minutes of the earliest one. Taps further out are ignored, so a conflict can stretch a ticket by at most 5 minutes. The result is worked out from the whole list of activations, so the order events arrive in doesn't change it. That means central and each edge now keep that short list per ticket instead of one timestamp. In your example, 10:31 and 10:42 resolve to 10:31; 10:31 and 10:34 would resolve to 10:34.
> - **Clock sync is now part of the design:**
>   - Buses take their time from GPS, which works with no network and after a bus has been parked or switched off. A battery-backed clock covers the gap after boot until the first GPS fix.
>   - Stations sync over their LAN.
>   - Each edge reports its clock offset to central when connected, and more than 5 seconds raises an alert. That 5-second bound is a new invariant (I7).
> - **Cooldown (FR6):** one short cooldown `c` everywhere, which I set to 2 minutes by default.
>   - **Side effect, please check:** enforcing it across different locations means every edge must know the card's last accepted tap. So every accepted tap is now synced, validations as well as activations, and I renamed the Activation Queue to **Tap Queue**. This roughly doubles the stream traffic, which the estimates still cover.
> - **Unused tickets (FR5):** a ticket must be activated within 1 calendar year of assignment. After that it expires and the card is free for a new ticket.
> - **Pass durations:** day, week and month passes now run for a fixed time from activation (24 hours, 7 days, 30 days), written into FR3.
> - **One ticket per card:** this is now part of FR4, and the "can't buy next month's pass early" question is closed.
> - **New "Accepted risks" section:**
>   - The station server is a single point of failure for its station. It shares a physical LAN with the gates and only goes down for routine maintenance.
>   - A bus that hasn't synced can accept a ticket that has already expired.
>   - A transfer made inside the cooldown is rejected.
>   - Ticket sales need the central system.
>
> **One new open question:** while a station server is down for maintenance, its gates can't decide taps. Should they stay closed, with staff letting riders through, or open freely?

---

## 3. Closing the last question

**User:**

> during maintenance, the gates are always open, benefit of doubt always given to the rider and none of the riders are left stranded

*Claude edited `docs/hld.md`: the accepted risk and the failure-mode row now say gates stay open, and the Open questions section was removed.*

**Claude:**

> I've added this to `ticket-validation-system/docs/hld.md`: during station server maintenance, gates stay open, so the rider always gets the benefit of the doubt and no one is stranded. It's in two places:
> - **Accepted risks:** the station server entry now says gates stay open for the whole maintenance window. It also says the cost: taps in that window aren't checked or recorded, so that revenue is lost.
> - **Failure modes:** the maintenance row now says "Gates stay open for the whole window".
>
> That was the last open question, so I removed the Open questions section. Nothing in the HLD is undecided now. Everything is still uncommitted. When you want to commit, I'll put it on a local `ticket-validation-system` branch, as the repo rules require.

---

## 4. This transcript

**User:**

> can you generate a transcript of this chat and put it in the docs directory for the channel viewers to see how i worked with claude to generate the hld from the flow diagram, name it as initial-hld-discussion.md
