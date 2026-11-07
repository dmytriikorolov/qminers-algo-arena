# Competition rule register

Rechecked **2026-11-06 23:17:40 Europe/Prague (22:17:40 UTC)**. This register distinguishes the published **Official Rules** from the **Technical Rules**, which Section 6 still says will be released at the opening briefing. Recheck both at the event; the Czech version prevails in a conflict (Section 17).

## Evidence

The public pages [home](https://arena.qminers.com/) and [rules](https://arena.qminers.com/rules) are JavaScript applications. The web text extractor returned no readable home text and could not open `/rules`. A fresh direct HTTPS request returned the HTML shell; its referenced [public application asset](https://arena.qminers.com/assets/index-D86aCFqk.js) contains the English and Czech rule texts. These were read as text, without executing the JavaScript or accessing authenticated endpoints. The HTML shell is 810 bytes, SHA-256 `fabf07ac3a008d722c4a18f0e7db8e4bc9dca8c6279c9adf0bf672217c3b915a`.

Evidence asset: `research/arena-index-D86aCFqk.js`, SHA-256 `9e5e2e20834be361b78077d9259b66a90096d5b570e5a9af549b1b0e3e534bd9`. This asset name/hash records the version actually examined; future deployments can change it. The full third-party application bundle is retained locally and ignored by Git; it is not part of our submission or redistributed source.

The fresh asset is byte-identical to that local copy (1,171,393 bytes). No public 2026 Technical Rules, strategy API/runtime specification, or official local evaluator was found in the checked public pages, linked asset, or public search. The asset contains submission-site API client code and a backtest-download field used by its login-protected dashboard; neither establishes the strategy callback contract, active limits, or scoring formula. No authenticated endpoints or guessed API paths were requested. Past-year QQH pages and unrelated sites named Quant Arena are not evidence for 2026. Follow [the morning integration checklist](MORNING_INTEGRATION_CHECKLIST.md) when organisers release the actual materials.

| Rule or question | Source and exact location | Status | Practical effect |
| --- | --- | --- | --- |
| Final implementation language | [Official Rules §6](https://arena.qminers.com/rules#sec-6), English and Czech text in asset | VERIFIED: Python | Build Python baselines. This does not establish a Python version. |
| AI, other languages, literature, public online sources during research/preparation/development | [§6](https://arena.qminers.com/rules#sec-6), second paragraph | VERIFIED: broadly permitted, subject to Technical Rules | This preparation is useful; recheck any technical restrictions before using it in a submission. |
| Prewritten code or pretrained weights admissible in the final submission | [§6 and §12](https://arena.qminers.com/rules#sec-6) | UNVERIFIED in detail | General tool permission is not an explicit approval of every prepared artifact. Obtain the Technical Rules and confirm. |
| Third-party material and licensing | [§12](https://arena.qminers.com/rules#sec-12) | VERIFIED: must comply with licence terms and Technical Rules | Do not paste archived AGPL code or unlicensed source into our submission. |
| Team size | [§3](https://arena.qminers.com/rules#sec-3) | VERIFIED: 2–4 members, one team per person | Acceptance confirmation establishes team composition; changes need organiser approval. |
| Participation location | [§4](https://arena.qminers.com/rules#sec-4) | VERIFIED: in person | Remote participation is prohibited. |
| Public task questions / advice from outside people during competition | [§6](https://arena.qminers.com/rules#sec-6) | VERIFIED: prohibited | Use organisers for clarifications. Do not post task questions publicly or seek a specific outside person's advice. |
| Sharing with other teams / manipulating evaluator | [§7](https://arena.qminers.com/rules#sec-7) | VERIFIED: prohibited | Keep team work independent; use only authorised interfaces. |
| Which rules govern scoring and technical operation | [§6](https://arena.qminers.com/rules#sec-6) | VERIFIED: Technical Rules take precedence in technical matters | Opening instructions control our API and evaluator, not past-year repos. |
| Exact scoring, ranking, tie-breaking | [§6 and §8](https://arena.qminers.com/rules#sec-8) | UNVERIFIED: deferred to Technical Rules | PnL appears in application UI, but is not enough to establish the scoring formula. |
| API, class/function signature, state persistence, execution mode | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | Official adapter remains unimplemented until a real contract is supplied. |
| Python version and permitted packages | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | Keep preparation dependency-light; test official environment separately. |
| CPU, RAM, time limits and determinism requirements | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | No 2025 limit is a 2026 fact. Measure locally, then enforce official limits. |
| Runtime networking, files, subprocesses | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | Development internet permission does not imply submitted code may use a network. Keep submission self-contained by default. |
| Dataset/external-data restrictions | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | Synthetic demos are preparation only; do not assume outside training data are admissible. |
| Submission number, deadlines, file-size/layout | [§6](https://arena.qminers.com/rules#sec-6) | UNVERIFIED | UI strings describe a single `.py`, configurable size/count and final selection. Confirm actual active values at briefing. |
| Final results and reruns | [§8](https://arena.qminers.com/rules#sec-8) | VERIFIED: leaderboards preliminary; organisers may inspect and rerun | Save exact artifacts/configs and reproducible evidence. |

## Questions for the opening briefing

1. May we reuse pre-event code, learned weights and public algorithms? Which third-party licences are acceptable?
2. What exact function/class, input/output schema and persistent state are supported?
3. Which Python/packages, CPU/RAM/wall-clock limits, filesystem/network restrictions and submission limits apply?
4. How are fills, fees, position limits, final valuation, scoring and ties defined? What official local evaluator can we run?
5. Which datasets and tools remain permissible under the released Technical Rules?

Prepared code is **not yet a verified contest submission**. The register is a reading of the published competition text, not a legal opinion.
