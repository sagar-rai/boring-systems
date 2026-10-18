# System Design Review

A transcript of the session in which the HLD ([`docs/hld.md`](../docs/hld.md)) was reviewed with the `sdr` (system design review) skill and the outcome written up as [`docs/finalized-sdr-hld.md`](../docs/finalized-sdr-hld.md). The user's messages are verbatim. Claude's replies are verbatim; its tool calls (reading files, writing the doc) are summarized in italics.

---

## 1. The ask

**User:**

> /sdr can you review the following hld `hld.md/Users/sagarrai/boring_systems/ticket-validation-system/docs/hld.md`
>
> this is the problem statement
> ```
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
> identifies itself. A card can have only one ticket at a time.
> ```

*Claude read `docs/hld.md`, the skill's review lenses and estimation reference, the earlier design transcript (for why the `y` merge rule and the shared cooldown were chosen) and the original flow notes, then wrote the review.*

**Claude:**

> ## Understanding
>
> **Problem:** 50 subway stations and 30 bus routes (about 300 buses), 2M trips/day. That works out to 23 taps/s on average, about 110/s in the peak hour and about 300/s in bursts. Tickets are assigned to an identity-only card at a station. A tap activates the ticket or validates it. Ticket types are single (`x` min), day, week and month. A card holds one ticket at a time.
>
> **Availability target:** neither the problem nor the HLD gives one. I assumed two defaults:
> - **Tap path:** must not depend on anything off-site, so taps keep working even when central is down.
> - **Sales:** 99.9%, which allows 43 min of downtime a month.
>
> **Design as I read it:**
> - Each of the 350 edges (50 station servers and about 300 bus computers) holds a full copy of card state and decides taps locally.
> - An accepted tap is committed to a local outbox before the gate opens, then shipped through a Tap Queue to central.
> - Central owns assignment, merges taps, and publishes full card state through an outbox and a replayable Status Queue to every edge.
>
> **Does it solve the problem?** Yes. Deciding taps at the edge from a full copy is the right approach for NFR1 to NFR3 at these numbers.
>
> ## What to change
>
> 1. **NFR5 depends on standby replication, and the design doesn't say which mode.** An activation leaves the edge outbox once central (or the Tap Queue) acknowledges it. With an async standby, a failover loses the last committed activations and assignments after they were acknowledged. That breaks "no activation is ever lost". It also leaves edges holding tickets that central no longer has, which breaks I1.
>    **Change:** use synchronous replication to the standby, and acknowledge only after the commit is on both. At 23 writes/s the extra latency doesn't matter. Also state what happens when the standby is down: block writes, or drop to async.
>
> 2. **Cross-edge cooldown (FR6) costs a lot and blocks nothing a per-edge cooldown wouldn't.** FR6 exists so "one card cannot carry two riders through at once". That passback happens at a single gate bank, and a physical card can't be at two edges within 2 minutes. Sharing the cooldown across edges still costs:
>    - every validation has to be synced (Decision 4), which doubles the stream to about 4M events/day and 16k deliveries/s;
>    - `last_tap_at` / `last_tap_edge` and I3 have to be replicated;
>    - the cooldown becomes a cross-device clock comparison;
>    - valid pass holders get rejected on bus-to-bus or bus-to-metro transfers inside `c`, which is your accepted risk.
>
>    **Change:** enforce `c` per edge from that edge's own taps, and sync only activations. "Short cooldown at all places", which you chose, is still met. The transfer-rejection risk goes away.
>
> 3. **There's no availability target, so the station-server risk can't be judged.** The stated handling assumes the server only goes down for planned maintenance. Disks, power supplies and OS hangs fail without warning, and then gates stay open for the whole repair time.
>    - Even at half of all trips, a station carries about 20k trips/day, roughly 1k an hour, that go unchecked.
>    - Single tickets used during that window stay unactivated and can be used again later.
>
>    **Change:** state targets for the tap path and for sales, plus an MTTR for an unplanned station-server failure. If a day-long repair doesn't fit, add a second station server per station that syncs on its own and that gates fail over to. That also removes the maintenance window.
>
> 4. **The `y` merge rule adds state that no requirement asks for.** FR3 measures validity from activation, and the activation that actually happened is the earliest one. The rule only matters when two unsynced edges activate within 5 minutes, and then the rider gains at most 5 minutes. To support that, a list of activations per ticket is replicated to 350 sites, along with an extra parameter and set-union merging (I2). `activated_at = min(...)` is just as order-independent and idempotent, and needs only one timestamp.
>    **Change:** you chose this rule earlier for rider experience, so keeping it is fine. This is the cost if you want to drop it.
>
> ## Failures they missed
>
> 1. **Payment succeeds but assignment fails.** I1 is checked after purchase completes (flow step 1, then step 3), so a rider whose current ticket hasn't expired can pay and then be refused. If the assign call times out, the office doesn't know whether the card got the ticket. A retry without an idempotency key (`ticket_id`) then fails I1 against its own first attempt.
>    - **Rider sees:** charged with no ticket.
>    - **Availability:** not affected.
> 2. **Edge storage full or failing,** for example flash wear on a bus computer. I5 forbids opening the gate without a commit, so that edge rejects every rider. That is the opposite of your benefit-of-the-doubt stance for station outages, and the HLD doesn't define it.
>    - **Rider sees:** everyone rejected on one bus or at one station.
>    - **Availability:** breaks the tap-path target for that edge.
> 3. **One edge stops applying updates while still online,** for example because its consumer is crash-looping, hits a message it can't parse, or has the wrong offset after a bootstrap. It keeps deciding on aging data, and nothing alerts, because only clock offset is monitored.
>    - **Rider sees:** newly bought tickets rejected at that edge indefinitely.
>    - **Availability:** breaks NFR4 there.
> 4. **A bad edge release reaches all 350 sites.** Every tap is decided by edge code, so one bad build rejects (or admits) riders across the whole city, and central redundancy doesn't help.
>    - **Rider sees:** rejected (or waved through) everywhere.
>    - **Availability:** breaks the tap-path target city-wide.
>
> ## A simpler design
>
> The two queues, both outbox workers and the Ingress Service can be replaced by the edge pulling changes from central over HTTP.
>
> **Theirs:** 9 components and 4 durable stores. A state change takes DB, then worker, then queue, then ingress, then Local DB.
>
> **Simpler:** 4 components and 2 stores.
>
> ```mermaid
> flowchart LR
>     office["Ticket Office"] -->|"assign"| central["Central Server"]
>     central <--> cdb[("Central DB<br/>primary + sync standby")]
>     reader["Turnstile / bus reader"] -->|"tap: card_id"| local
>     subgraph edge["Edge site: one per station, one per bus"]
>         local["Local Server"] <--> ldb[("Local DB")]
>     end
>     local -->|"GET card rows with seq > N"| central
>     local -->|"POST outbox taps, retried until acked"| central
> ```
>
> **How it works:**
> - **Central:** every write to a card row sets `seq` from a sequence. The card table becomes the change log, already compacted by `card_id`.
> - **Edge:** every few seconds it fetches rows with `seq > N`, merges them with the existing rules and stores N. It posts outbox taps in batches, keyed by `event_id`, and deletes them on a 2xx.
>
> **What it removes, and why each part isn't needed:**
>
> | Removed | Why it's not needed at these numbers |
> |---|---|
> | Status Queue (log, offsets, retention) | The `seq` column plus the N each edge stores do the same job. Retention doesn't exist, and bootstrap is just `seq > 0`, so there's no separate snapshot path. |
> | Tap Queue | The edge outbox is already durable and retried. The queue is a second buffer for the same events. |
> | Central Outbox Worker | The committed row is itself the event. |
> | Ingress Service | It becomes a sync loop inside the Local Server. |
>
> **Load it puts on central:**
> - 350 edges polling every 5 s is 70 range reads/s. Each read returns about 250 rows, or about 125 with change 2. Tap posts stay at 23/s or less on average.
> - That is far inside one primary.
> - NFR4 is met in about 5 s.
> - A bus reconnecting after 1 hour pulls about 165k rows, the same bytes as replaying their log.
>
> **The one thing to get right:** a poller can skip a row whose `seq` was allocated earlier but committed after a higher `seq` it has already read. Read only up to the oldest in-flight transaction, or add a safety lag of a few seconds. At 23 writes/s either is cheap, and it belongs in the LLD.
>
> **Trade-off:** none for the tap path. In both designs the edges go stale while central is down and taps keep working.
>
> Verdict: agree with changes

---

## 2. Persistence, purchase sync and replication

**User:**

> lets go through the questions one by one, i feel like the review is missing a major point which is making it so simple
> - direct post to the central server is a good suggestion, i feel like it does not cause any load issues due to volume but it does not act as persistent storage, the message queue can be considered as persistent storage and nothing will be lost
> - how do you do the outbox sync of ticket purchase
> - NFR5 depends on standby replication, and the design doesn't say which mode. An activation leaves the edge outbox once central (or the Tap Queue) acknowledges it. With an async standby, a failover loses the last committed activations and assignments after they were acknowledged. That breaks "no activation is ever lost". It also leaves edges holding tickets that central no longer has, which breaks I1.
>    Change: use synchronous replication to the standby, and acknowledge only after the commit is on both. At 23 writes/s the extra latency doesn't matter. Also state what happens when the standby is down: block writes, or drop to async.: this is an implementation detail

**Claude:**

> ## 1. Direct POST vs. a queue for persistence
>
> Removing the queue doesn't lose durability. The edge outbox is the persistent store on the edge side, and the Central DB is the persistent store on the other side. The edge deletes an outbox row only after central replies that the tap is committed. At every moment the event is durable in at least one place:
>
> ```
> edge outbox ──(until central's commit ack)──> Central DB
> ```
>
> A queue adds a third durable copy, but it doesn't shrink the risky window. The only way to lose an event is for the edge disk to die before the event leaves the edge. The event leaves the edge at the same moment either way, when it reaches the queue or when it reaches central. So the queue protects nothing that the outbox plus central doesn't already protect.
>
> The queue does help in one case: **central is down and the queue is up.** Edges can then drain into the queue, so events spend less time with the edge disk as their only copy. At these numbers an edge outbox holds hours of taps in a few MB, so the gain is small. And it only exists if the queue's availability doesn't depend on central.
>
> The queue also has the same ack question as the database. A queue that acknowledges before the write is replicated loses events on broker failover, just as an async standby does. So the queue doesn't remove the replication question from point 3, it moves it.
>
> ## 2. Outbox sync for ticket purchase
>
> There's no separate outbox. The card row is the outbox.
>
> 1. The assign transaction writes the card row and sets `seq = nextval(...)` in the same statement.
> 2. Each edge polls `GET /cards?after=N`, which returns rows with `seq > N` in `seq` order. It applies them with the merge rules and stores the highest `seq` it saw as the new N.
> 3. Tap merges also write the card row, so activations reach every edge through the same feed.
>
> A transactional outbox exists to make "state changed" and "event recorded" atomic. When the consumer reads the state table itself, there is only one write, so atomicity is automatic.
>
> **The one trap (your current Central Outbox Worker has it too):** sequence values are handed out before commit, not at commit.
>
> - Transaction A takes `seq 100` and transaction B takes `seq 101`.
> - B commits first, and an edge reads up to 101.
> - A then commits with 100, and every edge skips it permanently.
>
> Any worker that reads an outbox table by id has the same gap, unless it reads the DB's commit log instead.
>
> **Fix:** take `seq` from a counter row updated inside the transaction. The row lock serializes commits, so commit order matches `seq` order. Card writes run at roughly 46/s (assignments plus activation merges), and a transaction takes a few ms, so serializing them uses well under a third of one primary's capacity. This belongs in the LLD; the HLD needs only the invariant "a row's `seq` is visible only after every lower `seq` is."
>
> ## 3. Standby replication is an implementation detail
>
> I agree on the mechanism: the replication setting belongs in the LLD. The guarantee doesn't. Your Guarantees section says an activation stays "in the edge outbox until central acknowledges it", and that is only true if the acknowledgment means the commit is durable on two nodes. If it means one node, NFR5 is false as written. Reviewers check guarantees, so I'd add one invariant line to the HLD and nothing more:
>
> > I8 Central acknowledges a tap or an assignment only once it is durable on two nodes.
>
> It's your call. If you'd rather keep even that line out, I'll record NFR5 as resting on an LLD decision and move on.
>
> **Your decisions so far:**
> - Direct POST: accepted in principle. The queue-as-persistence question is answered above, so tell me if you still want the Tap Queue.
> - Pull sync for assignments: proposed above, waiting for you.
> - I8: your call, as above.
>
> Next up is change 2, the per-edge cooldown. Ready to go to it?

---

## 3. Pull sync and the network

**User:**

> pull sync is something i am still not convinced with for the assignment
> this relies too much on the network being available when the tap is done, i would prefer keeping a queue for updating assignment plus status updates, but activation can go as plain POST

**Claude:**

> Pull sync doesn't put the network on the tap path. The tap is decided from the Local DB in both designs, and the network is only used in the background to keep that copy current. The two designs behave the same:
>
> | | Queue (yours) | Pull |
> |---|---|---|
> | At tap time | Local DB only | Local DB only |
> | Edge offline | Updates wait in the queue under the edge's offset | Updates wait in the card table under the edge's `seq > N` |
> | Edge reconnects | Consumes from its offset | Fetches from its N |
> | Central down | No new assignments to deliver | No new assignments to deliver |
>
> The only differences are that a queue pushes in under a second where polling every 5 s takes about 5 s (NFR4 allows 60), and the queue costs three extra components: the queue, the outbox worker and the Ingress Service. It has no advantage for availability.
>
> If you still prefer the queue, I'll record that and move on. Your design then becomes:
>
> - **Status Queue, Central Outbox Worker and Ingress Service stay**, along with log retention and the snapshot bootstrap (Decision 7).
> - **Tap Queue is removed.** The Local Outbox Worker POSTs taps to central and deletes a row only after central confirms the commit.
> - **The `seq` gap from my last reply still matters:** your Central Outbox Worker reads the outbox table by id, so it needs the same fix (a counter row taken inside the transaction, or reading the DB's commit log).
>
> Keep the queue for status, or switch to pull? Once you answer, we'll go to change 2, the per-edge cooldown.

---

## 4. New cards and the Status Queue decision

**User:**

> the seq gap is something that is implementation details, and it would depend on the db choice and the query patterns, and is something for the LLD and implementation detail
> i would prefer the status queue, and the reason is
> - a new card_id gets issued and the edge has no information about it, so the pull does not actually work for the new(card_id) unless central DB has a way to informt the edge about the new card issuance, activation can go to post instead of a queue push, thanks

**Claude:**

> Agreed that the `seq` gap belongs in the LLD, so I'll leave it out of the HLD.
>
> On new cards: the pull doesn't look up a known `card_id`. It asks for every card row with `seq > N`, so a newly issued card shows up in the next poll like any other change. That's the last I'll say on it. Recorded: you're keeping the Status Queue, and activations go to central as a plain POST.
>
> **Decisions so far**
>
> | Item | Decision |
> |---|---|
> | Status Queue, Central Outbox Worker, Ingress Service | Kept |
> | Tap Queue | Removed. The Local Outbox Worker POSTs taps and deletes a row only after central confirms the commit. |
> | Replication mode and the `seq` gap | Go in the LLD. I8 (acknowledge only once a write is durable on two nodes) is still open, from point 3. |
> | Pull sync | Rejected |
>
> ## Change 2: per-edge cooldown
>
> FR6's purpose is "one card cannot carry two riders through at once". Passing the card back to a second rider happens at one gate bank, and a physical card can't be at two edges within `c` = 2 minutes. A cooldown checked only against the edge's own taps blocks the same misuse. It also removes these:
>
> - **Validations reaching other edges.** Only activations need to leave the edge, which cuts the stream from about 4M to about 2M events a day.
> - **`last_tap_at` and `last_tap_edge` in replicated state,** along with I3.
> - **Cross-device clock comparison for the cooldown.** Clocks then matter only for merging activations.
> - **The accepted risk that short transfers get rejected.** A pass holder changing buses within 2 minutes is no longer turned away.
>
> The one thing you give up: a cloned card used at two places at once is no longer caught. Card blocking is out of scope, so I'd accept that.
>
> Take the per-edge cooldown, or keep the shared one?

---

## 5. Confirming the revised design

**User:**

> so going back to change 1 again, is using the DB as a log table, and fetch all logs after a seq N, which have been performed and reconcile the state at the service level
> instead of storing the state we store the logs and compute the state, understood, but i would like to keep my design of outbox for status updates and post as you suggested for the activations, unless you see some issue with the design now, apart from two additional components

**Claude:**

> One correction on how you summarized my proposal: it wasn't event sourcing. Central still stores each card's current state as a row. The `seq` column only tells an edge which rows changed since its last poll, and the edge copies those rows as they are, with nothing recomputed. Either way, you've decided to keep the outbox, so I'll drop it.
>
> With activations sent as a POST, I see no other issue in your design. Each part of the revised flow holds up:
>
> - **Tap to central:** the edge commits the tap and its outbox row before the gate opens. It POSTs the tap and deletes the outbox row only after central confirms the commit. A retry is safe because central applies each `event_id` once (I6).
> - **Central down:** taps wait in the edge outboxes, which hold hours of traffic in a few MB. NFR5 holds as long as the edge disk survives, the same as before.
> - **Central to edges:** central writes the card row and its outbox row in one transaction. The worker publishes to the Status Queue and Ingress applies it. Messages carry full card state (Decision 8), so a repeated or out-of-order message is harmless.
>
> One ordering rule belongs in the HLD's invariants, because the bootstrap guarantee depends on it.
>
> > **Bootstrap:** record the queue offset *before* taking the snapshot, then replay from that offset.
>
> The overlap that ordering creates is harmless, because a full-state message can be applied twice safely. The reverse order loses data: a change that commits after the snapshot but is published before the offset is read appears in neither, and that edge never gets it.
>
> **Still open:**
>
> - I8 (central acknowledges a write only once it is durable on two nodes) from point 3: add the invariant line, or record it as an LLD decision?
> - Change 2: per-edge cooldown or the shared one?

---

## 6. Cooldown

**User:**

> we will keep the shared cool down for the ease of implementation

**Claude:**

> Recorded: the cooldown stays shared. One fact before moving on: the shared cooldown is the harder one to build. It needs every validation POSTed to central and fanned out, `last_tap_at` merged by max (I3), and clocks compared across devices. A per-edge cooldown reads one local column. Your decision stands either way.
>
> As a result, the POST carries every accepted tap, validations as well as activations, and the stream stays at about 4M events a day. The accepted risk that short transfers are rejected also stays.
>
> ## Change 3: availability target and the station server
>
> The HLD has no availability number, so the station-server risk can't be checked against anything. It assumes the server goes down only for planned maintenance. Disks, power supplies and OS hangs fail without warning, and the gates then stay open for the whole repair, which can take hours to a day rather than a maintenance window. Even if a station carries only half of an even share of trips, that is about 20k trips a day, roughly 1k an hour, unchecked and unrecorded. Single tickets used during the window also stay unactivated and can be used again later.
>
> **Proposed changes:**
>
> 1. **State two targets.** For example, taps should depend on nothing off-site, and sales should be up 99.9% of the time (43 min of downtime a month).
> 2. **Add unplanned station-server failure to the accepted risk,** with a target repair time and its revenue cost.
> 3. **If a day-long repair doesn't fit, add a second station server per station.** Both consume the Status Queue independently and gates fail over to the standby. This also removes the maintenance window.
>
> Which do you want: 1 and 2 only, or all three?

---

## 7. Availability and the station server

**User:**

> we will not consider change 3, its out of scope

**Claude:**

> Recorded: change 3 is out of scope. The HLD will have no availability target, and the station-server risk stays as written, covering maintenance only.
>
> ## Change 4: the `y` merge rule
>
> FR3 measures validity from activation, and the activation that really happened is the earliest one. The `y` rule matters in only one case: two edges that haven't synced each activate the same ticket within 5 minutes. Even then the rider gains at most 5 minutes. That small gain costs three things:
>
> - a list of activations per ticket, replicated to all 350 sites
> - set-union merging on `event_id` (I2)
> - an extra parameter, `y`
>
> Taking the earliest activation, `activated_at = min(...)`, is just as safe when events arrive out of order or twice, and it stores a single timestamp.
>
> You chose `y` earlier for the rider experience, so keeping it is a legitimate choice. Keep `y`, or switch to the earliest activation?
>
> **Still open:**
> - **I8:** central acknowledges a write only once it is durable on two nodes. Add it to the HLD as an invariant, or leave it as an LLD decision?
> - **Bootstrap rule:** record the queue offset before taking the snapshot. Should it go in the invariants?

---

## 8. Merge rule

**User:**

> we will keep the better rider experience due to the low risks and a small time window of 5 minutes

**Claude:**

> Recorded: the `y` rule stays, with `y` = 5 minutes.
>
> The four changes are settled. Next are the missed failures. For each one, decide whether to take it on (I'll then propose handling) or accept it as a risk.
>
> | # | Failure | What the rider sees | Blast radius |
> |---|---|---|---|
> | F1 | **Payment succeeds but assignment fails or times out.** I1 is checked after the purchase completes. A retry without `ticket_id` as an idempotency key fails I1 against its own first attempt. | Charged, with no ticket | One rider per occurrence |
> | F2 | **Edge storage full or failing.** I5 forbids opening without a commit, so that edge rejects everyone. This is the opposite of the stance the HLD takes when a station server is down: let riders through. | Everyone rejected | One bus or one station |
> | F3 | **An edge stops applying updates while still online.** Causes include a crash-looping Ingress, a message it can't parse, or a bad offset after bootstrap. Only clock offset is monitored, so nothing alerts. | New tickets rejected at that edge; NFR4 broken there | One edge, indefinitely |
> | F4 | **A bad edge release reaches all 350 sites.** Every tap is decided by edge code, and the central standby doesn't help. | Riders rejected or let through everywhere | Whole city |
>
> **Still open:**
> - **I8:** central acknowledges a write only once it is durable on two nodes. Add it to the HLD as an invariant, or leave it as an LLD decision?
> - **Bootstrap rule:** record the queue offset before taking the snapshot. Add it to the HLD's invariants?
>
> Which of F1 to F4 do you want to take on?

---

## 9. Missed failures

**User:**

> F1 is not possible due to the ticket assignment only possible when the central server is available: accepted risk
> F2: we wouldnt fix it, we will have centralized alerting suggesting which edge server needs the servicing
> F3: same as F2
> we will discuss F4

**Claude:**

> ## F1: payment succeeds, assignment fails
>
> I'll record it as an accepted risk, but it can happen while central is up, not only when it's down. In both cases below the purchase has already completed:
>
> - **Rejection:** the rider's card still holds an unexpired ticket, so central refuses the assignment because of I1.
> - **Timeout:** central is slow or the call drops, so the office can't tell whether the assignment went through. A retry without an idempotency key fails I1 against its own first attempt.
>
> **Recorded: accepted risk.**
>
> ## F2 and F3: centralized alerting
>
> Your alerts need a signal for each failure. The simplest is to extend the clock-offset report that edges already send. Each heartbeat carries:
>
> | Field | Catches |
> |---|---|
> | Applied Status Queue offset | F3: lag over 1 min while heartbeats are fresh, which is an NFR4 breach |
> | Free disk and local write errors | F2 |
> | Outbox depth | Taps not draining while the edge is connected |
> | Clock offset | I7, as today |
>
> Also alert when heartbeats stop arriving. A dead edge sends no report, and a bus that is merely offline also goes quiet, so use a longer threshold for buses.
>
> **Alternative for F3:** read consumer lag from the queue itself, with no change to the edge. This doesn't cover F2.
>
> **Recorded: F2 and F3 are handled by central alerting, not fixed.**
>
> ## F4: a bad edge release reaches all 350 sites
>
> Every tap is decided by edge code, so the release process is what limits the damage.
>
> **Proposed handling, a staged rollout with automatic rollback:**
>
> 1. **Canary:** one station and a few buses. Wait at least one peak hour and compare reject rate and crash count with the rest of the fleet.
> 2. **Waves:** if the canary is healthy, roll out to the remaining edges in batches. Watch the same metrics and pause automatically on regression.
> 3. **Automatic rollback:** each edge keeps the previous build and reverts to it if the new build fails its health check, for example a crash loop or a reject rate far above its own baseline.
>
> **Alternative:** manual waves with a fleet-wide pause switch. It's simpler to build, but rollback depends on someone noticing.
>
> **What the release process implies for the design:** edges will run mixed versions for days, because parked or offline buses update late. So:
>
> - the Status Queue message format must be readable by both the old and the new edge build;
> - the tap POST from an old edge build must still be accepted by central;
> - the Local DB schema change must be reversible, so an automatic rollback doesn't strand the data.
>
> This is the only part of F4 that belongs in the HLD, as one line under the failure table. The rollout mechanics belong in the LLD.
>
> **Still open:**
> - **F4:** take the staged rollout, the manual alternative, or something else?
> - **I8:** central acknowledges a write only once it is durable on two nodes. Add it to the HLD, or leave it as an LLD decision?
> - **Bootstrap rule:** record the queue offset before taking the snapshot. Add it to the HLD?

---

## 10. Edge releases

**User:**

> we will do canary based updates to the edge servers, and automatic rollback in case canary fails

**Claude:**

> Recorded for F4: edge releases go to a canary first, and edges roll back automatically if the canary fails.
>
> A canary means the fleet runs two edge versions at once, and parked buses can stay on the old one for days. The HLD should state that the Status Queue message format, the tap POST and the Local DB schema must work across both versions. Otherwise a rollback can strand data.
>
> Four items are still open before I write the final design:
>
> 1. **I8:** central acknowledges a write only once it is durable on two nodes. Should this go in the HLD's invariants, or stay a decision for the LLD?
> 2. **Bootstrap rule:** an edge records the queue offset before taking the snapshot. Should it go in the HLD's invariants?
> 3. **Mixed-version compatibility:** should the line above go under the failure table?
> 4. **Editing `docs/hld.md`:** should I apply all the recorded decisions to it, or only give you the final design here?

---

## 11. The finalized HLD and this transcript

**User:**

> there are no breaking updates in the message format and its out of scope for the hld
> you are creating a finalized-sdr-hld in the same folder and you need to create transcript as the sdr_transcript in the directory as the other transcript thanks

*Claude wrote `docs/finalized-sdr-hld.md`: the HLD with the Tap Queue replaced by a direct POST, an Operations section for edge heartbeats and canary releases, the paid-but-unassigned purchase as an accepted risk, new failure-mode rows, and a design review outcome section listing what changed, what was rejected with its cost, what is out of scope and what is left to the LLD. `docs/hld.md` was left as it was. Claude then wrote this transcript.*
