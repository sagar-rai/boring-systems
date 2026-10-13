# Estimation Reference

Orders of magnitude for back-of-envelope math, not benchmarks. Real limits depend on hardware, payload and query shape; say so when a decision hinges on one.

## Conversions
- 1 day = 86,400 s, round to 10^5 s.
- Average QPS = requests per day / 10^5.
- Peak QPS = 2 to 3x average for steady traffic, 10x or more for spiky traffic (launches, flash sales).
- 1 million requests/day is about 12 QPS average.
- 2^10 = 1 thousand, 2^20 = 1 million, 2^30 = 1 billion, 2^40 = 1 trillion.

## Availability budget
| Target | Downtime per month | Downtime per year |
|---|---|---|
| 99% | 7.2 h | 3.65 days |
| 99.9% | 43 min | 8.8 h |
| 99.95% | 22 min | 4.4 h |
| 99.99% | 4.3 min | 53 min |

Accepted downtime fits the budget when frequency x duration, summed over every accepted failure and planned deploy, stays under the monthly figure.

## Storage
- Storage = writes per day x record size x retention days x replication factor.
- Add indexes, usually 20 to 50% on top of row data.

## Bandwidth
- Bandwidth = QPS x payload size, for ingress and egress separately.

## Latency
| Operation | Rough latency |
|---|---|
| Main memory reference | 100 ns |
| Read 1 MB sequentially from memory | 10 us |
| SSD random read | 100 us |
| Round trip within a datacenter | 0.5 ms |
| Read 1 MB sequentially from SSD | 1 ms |
| Round trip across regions | 50 to 150 ms |

## Single-node throughput
| Component | Rough ceiling |
|---|---|
| Relational DB primary, simple indexed writes | 1k to 10k writes/s |
| Relational DB, indexed point reads | 10k to 50k reads/s, more with replicas |
| In-memory key/value store | 100k ops/s |
| Stateless app server, simple request | 1k to 10k req/s |
| Log-based broker partition | 10 to 100 MB/s |

A single relational database on decent hardware covers most problems below a few thousand writes per second. Reaching past it needs a number that says so.
