"""Versioned benchmark workloads: what work a benchmark request asks for.

A measurement is interpretable only together with the workload that produced
it: provider/model + workload id + origin + cache policy + time. This module is
the single owner of workload definitions. Each `Workload` fixes the benchmark
input (one prompt text) and the requested output cap, under a stable versioned
id that is stored with every attempt (`requests.workload_id`). The prompt text
itself is never stored; the id is the link back to this code.

Rules every definition follows:

- Versioned identity. A workload id names one exact prompt and output cap. If
  a change would make new measurements not directly comparable with old ones
  (different content, instructions, task, or cap), add a new version (e.g.
  `rag-v2`) and leave the old definition untouched; never edit a released
  version in place. `tests/test_workloads.py` pins a SHA-256 of every prompt
  to catch accidental edits.
- Deterministic content. Prompts are built here from original, synthetic
  material written for this benchmark (fictional organizations, people, and
  data), using plain string templates and integer arithmetic: no randomness,
  timestamps, environment, files, or network. Building one twice yields the
  same text on every machine.
- Same content, provider-specific token counts. Every provider receives the
  same prompt text for a workload version. Providers tokenize differently, so
  their reported input token counts differ; those counts are observed facts
  recorded from each provider's usage, never normalized away.
  `target_input_tokens` is only the approximate size this workload was
  designed for (about 4 characters per token of English text), not a count any
  provider will report.
- The output cap is a cap. `max_output_tokens` is the maximum requested from
  the provider, not a length the model must reach; the actual output token
  count is whatever the provider reports. Nothing retries or extends a
  response to reach the cap.
- Performance, not quality. These workloads shape requests (input size, task
  type, output size) for latency, throughput, reliability, and cost
  measurement. Answers are not graded.

The six benchmark workloads are candidate hypotheses about which application
shapes matter, not findings from user research; expect to add, re-version, or
retire them as evidence arrives. Retired ids stay valid in stored data.

This module imports nothing from llm_metrics: providers, measurement, storage,
analytics, and the web layer depend on it, never the reverse.
"""

import dataclasses
import re

# Benchmark workload categories (application shapes), plus "smoke": a minimal
# connectivity check for a real provider, not a benchmark workload.
CATEGORIES = (
    "interactive_chat",
    "coding",
    "rag",
    "summarization",
    "extraction",
    "agent_tool",
    "smoke",
)

# Lowercase words separated by "-", "." or "_", ending in a version suffix.
_WORKLOAD_ID = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*[.-]v[1-9][0-9]*")


@dataclasses.dataclass(frozen=True)
class Workload:
    """One versioned benchmark workload.

    Attributes:
        workload_id: Stable identity stored with every attempt, ending in its
            version, e.g. "rag-v1".
        category: One of `CATEGORIES`.
        version: Version number; the id's suffix.
        name: Short human-readable name.
        description: What the workload represents and how it is shaped.
        prompt: The complete benchmark input sent to the provider. Never
            stored or printed.
        max_output_tokens: Output token cap requested from the provider.
        target_input_tokens: Approximate designed input size in tokens. A
            design target, not a provider-reported count.
    """

    workload_id: str
    category: str
    version: int
    name: str
    description: str
    prompt: str
    max_output_tokens: int
    target_input_tokens: int

    def __post_init__(self):
        """Rejects incoherent definitions when the catalogue is built.

        Raises:
            ValueError: If the id is not a versioned id matching `version`,
                the category is unknown, a text field is blank, or a size is
                not positive.
        """
        if not _WORKLOAD_ID.fullmatch(self.workload_id) or not (
            self.workload_id.endswith(f"v{self.version}")
        ):
            raise ValueError("workload_id must be versioned and match version.")
        if self.category not in CATEGORIES:
            raise ValueError("category must be one of CATEGORIES.")
        for text in (self.name, self.description, self.prompt):
            if not text.strip():
                raise ValueError("name, description and prompt are required.")
        if self.max_output_tokens < 1 or self.target_input_tokens < 1:
            raise ValueError("Token sizes must be positive.")


class UnknownWorkloadError(ValueError):
    """The requested workload id is not in the catalogue."""


# Invented names used to fill the synthetic material. Picking with
# `_pick(values, index, step)` makes every generated line deterministic and
# varied without randomness.
_NAMES = (
    "Alder",
    "Brisk",
    "Cobalt",
    "Dunmore",
    "Eskar",
    "Fennel",
    "Garnet",
    "Hollin",
    "Isel",
    "Juniper",
    "Kestrel",
    "Larch",
    "Morrow",
    "Nettle",
    "Oriel",
    "Pellan",
    "Quarry",
    "Rowan",
    "Sorrel",
    "Tamsin",
    "Umber",
    "Vesper",
    "Wren",
    "Yarrow",
)
_PLACES = (
    "Harbor Street",
    "North Quay",
    "Millbrook",
    "Old Foundry",
    "Riverside",
    "Upper Terrace",
    "Station Square",
    "Lantern Hill",
    "Westgate",
    "Ferry Point",
    "Orchard Lane",
    "Granite Row",
)


def _pick(values: tuple[str, ...], index: int, step: int = 1) -> str:
    return values[(index * step) % len(values)]


def _interactive_chat_prompt() -> str:
    """A support-chat context plus a question needing a moderate explanation."""
    settings = []
    for i in range(24):
        name = _pick(_NAMES, i, 5).lower()
        settings.append(
            f"- Setting `sync.{name}_{i + 1:02d}` (Preferences > Sync >"
            f" {_pick(_NAMES, i, 7)}): default {'on' if i % 3 else 'off'},"
            f" retry interval {15 + (i * 7) % 45} seconds. When enabled,"
            f" notes in the {_pick(_NAMES, i, 11)} notebook are checked for"
            f" remote changes every {2 + i % 5} minutes and local edits are"
            f" queued for upload in batches of {10 + (i * 3) % 20}."
        )
    turns = [
        (
            "User",
            "Hi! I use Lumen Notes on my laptop and my phone. Yesterday I"
            " edited the same shopping list on both while I was on a train"
            " with no signal.",
        ),
        (
            "Assistant",
            "Thanks for the details. Editing the same note on two devices"
            " while both are offline is exactly the case where Lumen Notes"
            " has to reconcile two versions once they reconnect.",
        ),
        (
            "User",
            "When I got home, the phone showed a banner saying a conflict"
            " copy was created. The laptop showed only my laptop edits.",
        ),
        (
            "Assistant",
            "That banner means the phone uploaded second. Lumen Notes keeps"
            " the version that reached the server first as the main note and"
            " saves the other device's edits as a separate conflict copy in"
            " the same notebook, so nothing is silently discarded.",
        ),
        (
            "User",
            "Okay. I found the conflict copy. I merged the items by hand and"
            " deleted the copy. Is that the right thing to do?",
        ),
        (
            "Assistant",
            "Yes, merging by hand and then deleting the copy is safe once"
            " the main note contains everything you want to keep.",
        ),
    ]
    history = "\n\n".join(f"{speaker}: {text}" for speaker, text in turns)
    return (
        "You are the support assistant for Lumen Notes, a fictional"
        " note-taking app used on laptops and phones. Answer in plain"
        " language, be friendly and precise, and refer to settings by their"
        " exact names when they matter.\n\n"
        "Product facts:\n"
        "- Lumen Notes stores every note on the device first and syncs it"
        " to the user's account when a connection is available.\n"
        "- Each edit is recorded with the device name and the time it was"
        " made on that device.\n"
        "- When two devices change the same note before either has synced,"
        " the first upload wins and the second becomes a conflict copy"
        ' named "<note title> (conflict from <device>)".\n'
        "- Conflict copies are never merged automatically.\n"
        "- Version history keeps the last 30 days of versions for each"
        " note.\n\n"
        "Sync settings reference:\n" + "\n".join(settings) + "\n\n"
        "Conversation so far:\n\n" + history + "\n\n"
        "User: Can you explain, step by step, what exactly happens during"
        " sync when I edit a note offline on two devices, how I can recover"
        " an older version if I merge something wrongly, and which settings"
        " I should change to make conflicts less likely in the future?\n\n"
        "Assistant:"
    )


def _coding_prompt() -> str:
    """A small fictional Python codebase plus a debugging/fix request."""
    modules = []
    for i in range(41):
        name = _pick(_NAMES, i, 5).lower()
        place = _pick(_PLACES, i, 7)
        modules.append(
            f"# --- inventory/{name}_{i + 1:02d}.py ---\n"
            f'"""Stock rules for the {place} depot (site {100 + i})."""\n\n'
            "import dataclasses\n\n\n"
            "@dataclasses.dataclass(frozen=True)\n"
            f"class {_pick(_NAMES, i, 5)}{i + 1:02d}Rule:\n"
            f'    """Reorder rule for depot site {100 + i}."""\n\n'
            f"    minimum_units: int = {5 + (i * 7) % 40}\n"
            f"    reorder_batch: int = {20 + (i * 13) % 80}\n"
            f"    lead_time_days: int = {1 + i % 9}\n\n"
            "    def needs_reorder(self, on_hand: int, reserved: int)"
            " -> bool:\n"
            "        available = on_hand - reserved\n"
            "        return available < self.minimum_units\n\n"
            "    def order_size(self, on_hand: int, reserved: int) -> int:\n"
            "        if not self.needs_reorder(on_hand, reserved):\n"
            "            return 0\n"
            "        shortfall = self.minimum_units - (on_hand - reserved)\n"
            "        batches = -(-shortfall // self.reorder_batch)\n"
            "        return batches * self.reorder_batch\n"
        )
    allocator = (
        "# --- inventory/allocate.py ---\n"
        '"""Splits one customer order across depots."""\n\n\n'
        "def allocate_stock(order_units, depots):\n"
        '    """Allocates `order_units` from depots in priority order.\n\n'
        "    Args:\n"
        "        order_units: Units the customer ordered (>= 0).\n"
        "        depots: List of (depot_name, on_hand, reserved) tuples in\n"
        "            priority order.\n\n"
        "    Returns:\n"
        "        Dict depot_name -> units taken. Never takes reserved units\n"
        "        and never takes more than ordered.\n"
        '    """\n'
        "    allocation = {}\n"
        "    remaining = order_units\n"
        "    for name, on_hand, reserved in depots:\n"
        "        available = on_hand - reserved\n"
        "        take = min(remaining, on_hand)\n"
        "        if take > 0:\n"
        "            allocation[name] = take\n"
        "        remaining -= take\n"
        "        if remaining == 0:\n"
        "            break\n"
        "    return allocation\n\n\n"
        "# --- tests/test_allocate.py ---\n"
        "def test_reserved_units_are_never_allocated():\n"
        '    depots = [("north", 10, 8), ("south", 20, 0)]\n'
        '    assert allocate_stock(5, depots) == {"north": 2, "south": 3}\n'
    )
    return (
        "You are reviewing a small Python codebase for a fictional"
        " warehouse company. The depot rule modules below are correct and"
        " are included for context. One function in inventory/allocate.py"
        " has a bug, and its test fails.\n\n"
        + "\n\n".join(modules)
        + "\n\n"
        + allocator
        + "\n\nTask:\n"
        "1. Explain why test_reserved_units_are_never_allocated fails.\n"
        "2. Give a corrected allocate_stock, keeping its signature and"
        " docstring.\n"
        "3. Point out any other input (for example a depot whose reserved"
        " units exceed its stock) that the corrected version must handle,"
        " and show how your version handles it.\n"
        "4. Add two more unit tests in the same style.\n"
    )


def _rag_prompt() -> str:
    """A transit knowledge base plus a question answerable from it."""
    articles = []
    for i in range(145):
        route = 10 + i
        start = _pick(_PLACES, i, 5)
        end = _pick(_PLACES, i + 3, 7)
        if i % 4:
            access = "available at every stop"
        else:
            access = f"not yet available at the {start} stop"
        articles.append(
            f"[Document {i + 1}] Route {route} ({_pick(_NAMES, i, 7)} Line)\n"
            f"Route {route} runs from {start} to {end}. On weekdays the first"
            f" bus leaves at {5 + i % 2}:{(i * 7) % 60:02d} and buses run"
            f" every {6 + (i * 5) % 19} minutes until 20:00, then every"
            f" {15 + (i * 3) % 16} minutes until the last departure at"
            f" {22 + i % 2}:{(i * 11) % 60:02d}. On weekends the service runs"
            f" every {12 + (i * 7) % 18} minutes. The route has"
            f" {8 + (i * 13) % 27} stops and a typical end-to-end journey"
            f" takes {18 + (i * 17) % 50} minutes. Step-free access is"
            f" {access}. Fares follow the standard zone"
            f" {1 + i % 3} tariff.\n"
        )
    return (
        "Answer the question using only the documents below, which describe"
        " the fictional Meridian Valley Transit network. If the documents do"
        " not contain the answer, say so. Cite the document numbers you"
        " used.\n\n"
        + "\n".join(articles)
        + "\nQuestion: A wheelchair user needs to travel on a Saturday"
        " morning using Route 14 and then Route 47. For each route, how"
        " often does the bus run on weekends, how long is the typical"
        " journey, and is step-free access available at every stop? Then"
        " estimate the total travel time including one average wait for"
        " each bus, and explain your estimate.\n"
    )


def _summarization_prompt() -> str:
    """A long document of monthly committee minutes plus a summary request."""
    departments = (
        "Water supply",
        "Road maintenance",
        "Parks and gardens",
        "Library services",
        "Waste collection",
        "Community events",
    )
    sections = []
    for month in range(36):
        for d, department in enumerate(departments):
            i = month * len(departments) + d
            lead = _pick(_NAMES, i, 7)
            planned = 20 + (i * 5) % 25
            completed = planned - (i * 7) % (planned // 2 + 1)
            filed = 3 + (i * 11) % 40
            resolved = filed - (i * 3) % (filed // 2 + 1)
            sections.append(
                f"## Year {month // 12 + 1}, month {month % 12 + 1}:"
                f" {department}\n"
                f"Reported by coordinator {lead} of the {_pick(_PLACES, i, 5)}"
                f" office. The team completed {completed} of {planned}"
                " planned tasks this month. Spending was"
                f" {40 + (i * 13) % 55} thousand credits against a monthly"
                f" budget of {60 + (i * 3) % 30} thousand credits. Residents"
                f" filed {filed} requests, of which {resolved} were resolved"
                " within a week. The"
                f" committee discussed staffing: {1 + i % 4} positions remain"
                f" open, and {lead} proposed sharing equipment with the"
                f" {_pick(_PLACES, i, 11)} office to reduce costs. A vote on"
                f" the proposal was {'approved' if i % 3 else 'postponed'} by"
                f" {5 + i % 4} votes to {i % 3}. Risks noted: "
                + (
                    "delayed deliveries of spare parts"
                    if i % 2
                    else "volunteer availability during holidays"
                )
                + f". Next review in month {(month + 1) % 12 + 1}.\n"
            )
    return (
        "The text below is three years of committee minutes from the fictional"
        " town of Elmsworth. Write a structured summary with these"
        " headings: Overview (3 sentences), Per-department highlights (one"
        " bullet per department covering task completion, spending against"
        " budget, and resident requests), Decisions taken, Recurring risks,"
        " Trends across the three years, and Open questions. Use only facts"
        " from the minutes.\n\n# Elmsworth Town Committee minutes\n\n"
        + "\n".join(sections)
    )


def _extraction_prompt() -> str:
    """Semi-structured shipment notices plus a field-extraction request."""
    notices = []
    for i in range(55):
        notices.append(
            f"--- Notice {i + 1} ---\n"
            f"From: dispatch@{_pick(_NAMES, i, 5).lower()}-freight.example\n"
            f"Subject: Shipment {4000 + i * 37} update\n"
            f"Hello {_pick(_NAMES, i, 7)} team, shipment {4000 + i * 37}"
            f" (pallets: {1 + (i * 3) % 12}, weight: {120 + (i * 53) % 900}"
            " kg) left"
            f" the {_pick(_PLACES, i, 5)} yard and is now expected at"
            f" {_pick(_PLACES, i, 7)} on day {1 + (i * 5) % 28} of next"
            " month. "
            + (
                "The driver reported minor damage to one pallet; please"
                " inspect on arrival. "
                if i % 5 == 0
                else ""
            )
            + (
                "Customs paperwork is still missing and must be sent before"
                " dispatch. "
                if i % 7 == 3
                else ""
            )
            + f"Reference code: {_pick(_NAMES, i, 3).upper()}-"
            f"{i * 91 % 1000:03d}.\n"
        )
    return (
        "Classify every shipment notice below into exactly one category:"
        ' "on_time", "damage_reported", or "paperwork_missing" (use'
        ' "damage_reported" if both problems are mentioned). Return only one'
        ' JSON object, with no other text: {"counts": {<category>:'
        ' <integer>, ...}, "needs_action": [<shipment id string>, ...]},'
        ' where "needs_action" lists, in notice order, the shipment ids of'
        ' every notice not classified "on_time".\n\n' + "\n".join(notices)
    )


def _agent_tool_prompt() -> str:
    """A tool catalogue and task state plus a next-action decision."""
    verbs = ("get", "list", "search", "update", "create", "cancel")
    nouns = (
        "inspection",
        "technician",
        "slot",
        "site",
        "work_order",
        "vehicle",
        "part",
        "invoice",
    )
    regions = ("north", "south", "east", "west")
    tools = []
    tool_names = []
    for i in range(66):
        verb = verbs[i % len(verbs)]
        noun = nouns[(i // len(verbs)) % len(nouns)]
        system = _pick(_NAMES, i, 5).lower()
        read_only = verb in ("get", "list", "search")
        side_effects = "none" if read_only else "changes stored records"
        tool_names.append(f"{verb}_{noun}_{system}")
        tools.append(
            f"Tool {i + 1}: {tool_names[-1]}\n"
            f"  Purpose: {verb.capitalize()} {noun.replace('_', ' ')} records"
            f" in the {system.capitalize()} scheduling system, which serves"
            f" the {_pick(_PLACES, i, 7)} area.\n"
            f"  Parameters: {noun}_id (string, optional), region (string,"
            f" one of {'/'.join(regions)}), status (string, optional), limit"
            f" (integer, 1-{10 + (i * 7) % 90}, default {5 + i % 10}),"
            f" dry_run (boolean, default {'true' if i % 2 else 'false'}).\n"
            f"  Returns: matching {noun.replace('_', ' ')} records with id,"
            " status, region and last_updated.\n"
            f"  Cost per call: {1 + (i * 3) % 9} credits. Side effects:"
            f" {side_effects}.\n"
        )
    # Earlier read-only calls: each names a listed tool whose verb is get,
    # list, or search (the first three verbs).
    log = []
    for step in range(12):
        i = (step * 13) % 66 // len(verbs) * len(verbs) + step % 3
        log.append(
            f"Step {step + 1}: called {tool_names[i]} with region"
            f" {regions[step % 4]} -> {3 + (step * 7) % 12} records, status"
            " ok."
        )
    return (
        "You are a planning agent for a fictional maintenance company. You"
        " can call the tools listed below. Do not call anything yet."
        " Decide the single best next tool call.\n\n"
        "Available tools:\n" + "\n".join(tools) + "\n"
        "Actions taken so far:\n" + "\n".join(log) + "\n\n"
        "Goal: reschedule every cancelled inspection in the north region to"
        " the next free slot, spending as few credits as possible and"
        " without changing any record until you have confirmed which"
        " inspections are affected.\n\n"
        "Reply with: (1) a short reasoning paragraph, (2) the chosen tool"
        " name, (3) its arguments as a JSON object, and (4) what you will do"
        " with the result.\n"
    )


INTERACTIVE_CHAT_V1 = Workload(
    workload_id="interactive-chat-v1",
    category="interactive_chat",
    version=1,
    name="Interactive chat",
    description=(
        "Conversational assistant: a product-support system context, a"
        " short conversation history, and a question that needs a"
        " moderate step-by-step explanation."
    ),
    prompt=_interactive_chat_prompt(),
    max_output_tokens=300,
    target_input_tokens=2_000,
)
CODING_V1 = Workload(
    workload_id="coding-v1",
    category="coding",
    version=1,
    name="Coding assistant",
    description=(
        "Code generation/debugging: a small multi-file Python codebase with"
        " one buggy function and its failing test; asks for a diagnosis, a"
        " fix, edge cases, and new tests."
    ),
    prompt=_coding_prompt(),
    max_output_tokens=1_000,
    target_input_tokens=8_000,
)
RAG_V1 = Workload(
    workload_id="rag-v1",
    category="rag",
    version=1,
    name="RAG / Q&A",
    description=(
        "Answering from supplied context: 145 retrieved transit documents"
        " and a question that combines facts from two of them, with"
        " citations."
    ),
    prompt=_rag_prompt(),
    max_output_tokens=500,
    target_input_tokens=16_000,
)
SUMMARIZATION_V1 = Workload(
    workload_id="summarization-v1",
    category="summarization",
    version=1,
    name="Long-document summarization",
    description=(
        "Long-document summarization: three years of committee minutes"
        " (216 sections) and a request for a structured summary under fixed"
        " headings."
    ),
    prompt=_summarization_prompt(),
    max_output_tokens=1_000,
    target_input_tokens=32_000,
)
EXTRACTION_V1 = Workload(
    workload_id="extraction-v1",
    category="extraction",
    version=1,
    name="Structured extraction / classification",
    description=(
        "Structured extraction/classification: 55 semi-structured shipment"
        " notices; asks for one category per notice, returned as a small"
        " JSON object of counts and flagged shipment ids (plain text, no"
        " provider structured-output feature)."
    ),
    prompt=_extraction_prompt(),
    max_output_tokens=150,
    target_input_tokens=4_000,
)
AGENT_TOOL_V1 = Workload(
    workload_id="agent-tool-v1",
    category="agent_tool",
    version=1,
    name="Agent / tool selection",
    description=(
        "Agent-style planning: a catalogue of 66 tools, a log of earlier"
        " actions, and a goal; asks for the single best next tool call as"
        " text (no provider-native tool calling)."
    ),
    prompt=_agent_tool_prompt(),
    max_output_tokens=300,
    target_input_tokens=8_000,
)
# The real-provider smoke check (`python -m llm_metrics.real_smoke`): the
# smallest useful real request. Its id predates this catalogue; v2 is the
# version first sent with OpenAI's prompt-caching control, so the id also
# stands for that request shape.
SMOKE_SHORT_TEXT_V2 = Workload(
    workload_id="smoke.short_text.v2",
    category="smoke",
    version=2,
    name="Smoke check",
    description=(
        "Connectivity check, not a benchmark workload: one short harmless"
        " sentence."
    ),
    prompt="Reply with one short friendly sentence greeting a benchmark tool.",
    max_output_tokens=64,
    target_input_tokens=15,
)

# The candidate benchmark workloads, in catalogue order.
BENCHMARK_WORKLOADS = (
    INTERACTIVE_CHAT_V1,
    CODING_V1,
    RAG_V1,
    SUMMARIZATION_V1,
    EXTRACTION_V1,
    AGENT_TOOL_V1,
)
# Workload run by `python -m llm_metrics` (and so `./run.sh`) by default:
# representative and still fast with the simulated provider.
DEFAULT_WORKLOAD_ID = INTERACTIVE_CHAT_V1.workload_id

_CATALOGUE = {
    workload.workload_id: workload
    for workload in (*BENCHMARK_WORKLOADS, SMOKE_SHORT_TEXT_V2)
}


def list_workloads() -> tuple[Workload, ...]:
    """Returns every runnable workload: the benchmark six, then the smoke."""
    return tuple(_CATALOGUE.values())


def get_workload(workload_id: str) -> Workload:
    """Returns the canonical definition of `workload_id`.

    Raises:
        UnknownWorkloadError: If the id is not in the catalogue. The message
            lists the valid ids and never repeats the requested one.
    """
    try:
        return _CATALOGUE[workload_id]
    except KeyError:
        raise UnknownWorkloadError(
            "Unknown workload. Valid workloads: " + ", ".join(_CATALOGUE) + "."
        ) from None
