"""Chat flow: the agent asks for contrasts/read length and uses the user's answer."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import src.db.models  # noqa: F401
from src.agents.orchestrator import ChatDispatchInput, OrchestratorAgent
from src.db.base import Base
from src.db.enums import MessageRole, SampleType
from src.db.models.auth import APIKey
from src.db.models.conversation import ChatMessage, Conversation
from src.db.models.genome import ReferenceGenome
from src.db.models.project import Project, RunSample, Sample
from src.db.models.run import AnalysisRun

CONDS = ("ctrl", "ctrl", "drugA", "drugA", "drugB", "drugB")


@pytest.fixture
def world():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        key = APIKey(key_hash=uuid.uuid4().hex, name="k", created_by="t", principal="t")
        project = Project(name="p", owner="t")
        genome = ReferenceGenome(
            name="GRCh38", species="Homo sapiens", build="hg38", fasta_path="/f", gtf_path="/g"
        )
        db.add_all([key, project, genome])
        db.flush()
        samples = [
            Sample(
                project_id=project.id,
                name=f"S{i}",
                sample_type=SampleType.bulk_rnaseq,
                condition=c,
                fastq_r1_path=f"/d/S{i}.fq",
                is_paired_end=False,
            )
            for i, c in enumerate(CONDS)
        ]
        conv = Conversation(created_by=key.id)
        db.add_all([*samples, conv])
        db.commit()
        yield SimpleNamespace(db=db, key=key, genome=genome, samples=samples, conv=conv)


def _say(w, text: str) -> ChatDispatchInput:  # type: ignore[no-untyped-def]
    msg = ChatMessage(conversation_id=w.conv.id, role=MessageRole.user, content=text)
    w.db.add(msg)
    w.db.commit()
    return ChatDispatchInput(
        conversation_id=str(w.conv.id),
        message_id=str(msg.id),
        user_content=text,
        api_key_id=str(w.key.id),
    )


def _llm(intent: dict) -> MagicMock:
    """Fake OpenAI client: JSON-mode call returns ``intent``; streaming call says 'Queued.'"""

    def create(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("stream"):
            delta = SimpleNamespace(content="Queued.")
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])
        msg = SimpleNamespace(content=json.dumps(intent))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    return client


def _intent(w, stages: list[str], contrasts: list[dict], read_length=None) -> dict:  # type: ignore[no-untyped-def]
    return {
        "type": "run",
        "run_name": "chat run",
        "genome_id": str(w.genome.id),
        "sample_ids": [str(s.id) for s in w.samples],
        "pipeline_type": "bulk_rnaseq",
        "stages": stages,
        "de_contrasts": contrasts,
        "read_length": read_length,
    }


DE_STAGES = ["qc", "alignment", "quantification", "differential_expression"]


async def test_asks_for_contrasts_listing_conditions(world) -> None:  # type: ignore[no-untyped-def]
    redis = AsyncMock()
    agent = OrchestratorAgent(_llm(_intent(world, DE_STAGES, [])))
    out = await agent.dispatch_from_chat(
        _say(world, "Run differential expression on all samples"), world.db, redis
    )

    assert out.needs_clarification and out.run_id is None
    assert "**drugA** (2 samples)" in out.clarification_prompt
    assert "`<test> vs <reference>`" in out.clarification_prompt
    assert world.db.query(AnalysisRun).count() == 0
    frames = [json.loads(c.args[1]) for c in redis.publish.call_args_list]
    assert frames[0]["payload"]["token"] == out.clarification_prompt
    assert frames[-1] == {
        "type": "done",
        "payload": {"message_id": out.assistant_message_id, "run_id": None},
    }


async def test_answer_creates_run_with_user_contrasts(world) -> None:  # type: ignore[no-untyped-def]
    await OrchestratorAgent(_llm(_intent(world, DE_STAGES, []))).dispatch_from_chat(
        _say(world, "Run differential expression on all samples"), world.db
    )

    contrasts = [
        {"numerator": "drugA", "denominator": "ctrl"},
        {"numerator": "drugB", "denominator": "ctrl"},
    ]
    llm = _llm(_intent(world, DE_STAGES, contrasts))
    out = await OrchestratorAgent(llm).dispatch_from_chat(
        _say(world, "drugA vs ctrl and drugB vs ctrl"), world.db
    )

    assert not out.needs_clarification and out.run_id
    run = world.db.get(AnalysisRun, uuid.UUID(out.run_id))
    assert run.run_config["de_contrasts"] == [
        {"name": "drugA_vs_ctrl", "numerator": "drugA", "denominator": "ctrl"},
        {"name": "drugB_vs_ctrl", "numerator": "drugB", "denominator": "ctrl"},
    ]
    assert world.db.query(RunSample).filter_by(run_id=run.id).count() == len(CONDS)

    # The earlier request and the follow-up question were sent to the LLM as history.
    intent_call = next(
        c for c in llm.chat.completions.create.call_args_list if "response_format" in c.kwargs
    )
    roles = [m["role"] for m in intent_call.kwargs["messages"]]
    assert roles == ["system", "user", "assistant", "user"]

    reply = world.db.get(ChatMessage, uuid.UUID(out.assistant_message_id)).content
    assert "**drugA** vs **ctrl**" in reply


async def test_contrast_the_user_never_named_is_not_used(world) -> None:  # type: ignore[no-untyped-def]
    # LLM invents a direction although the user only said "compare the groups".
    invented = [{"numerator": "drugA", "denominator": "ctrl"}]
    out = await OrchestratorAgent(_llm(_intent(world, DE_STAGES, invented))).dispatch_from_chat(
        _say(world, "compare the groups please"), world.db
    )
    assert out.needs_clarification and out.run_id is None
    assert "couldn't match" in out.clarification_prompt


async def test_unknown_condition_triggers_question(world) -> None:  # type: ignore[no-untyped-def]
    contrasts = [{"numerator": "drugC", "denominator": "ctrl"}]
    out = await OrchestratorAgent(_llm(_intent(world, DE_STAGES, contrasts))).dispatch_from_chat(
        _say(world, "drugC vs ctrl"), world.db
    )
    assert out.needs_clarification
    assert "drugC" in out.clarification_prompt


async def test_read_length_must_come_from_user(world) -> None:  # type: ignore[no-untyped-def]
    stages = ["alignment", "splicing"]
    contrasts = [{"numerator": "drugA", "denominator": "ctrl"}]

    # LLM hallucinates 150, user never said it → ask.
    out = await OrchestratorAgent(
        _llm(_intent(world, stages, contrasts, read_length=150))
    ).dispatch_from_chat(_say(world, "splicing for drugA vs ctrl"), world.db)
    assert out.needs_clarification and "read length" in out.clarification_prompt

    # User answers → run created with their value.
    out = await OrchestratorAgent(
        _llm(_intent(world, stages, contrasts, read_length=150))
    ).dispatch_from_chat(_say(world, "150 bp"), world.db)
    assert out.run_id
    assert world.db.get(AnalysisRun, uuid.UUID(out.run_id)).run_config["read_length"] == 150


# ── Data isolation (safety Rule 12) ────────────────────────────────────────────


def _foreign_sample(w) -> Sample:  # type: ignore[no-untyped-def]
    other = Project(name="someone else's", owner="team_b")
    w.db.add(other)
    w.db.flush()
    sample = Sample(
        project_id=other.id,
        name="FOREIGN_SAMPLE",
        sample_type=SampleType.bulk_rnaseq,
        condition="ctrl",
        fastq_r1_path="/d/foreign.fq",
        is_paired_end=False,
    )
    w.db.add(sample)
    w.db.commit()
    return sample


async def test_foreign_samples_not_offered_to_llm(world) -> None:  # type: ignore[no-untyped-def]
    foreign = _foreign_sample(world)
    llm = _llm({"type": "clarification", "question": "Which samples?"})
    await OrchestratorAgent(llm).dispatch_from_chat(_say(world, "hi"), world.db, AsyncMock())

    system_prompt = llm.chat.completions.create.call_args_list[0].kwargs["messages"][0]["content"]
    assert "S0" in system_prompt
    assert "FOREIGN_SAMPLE" not in system_prompt
    assert str(foreign.id) not in system_prompt


async def test_foreign_sample_id_from_llm_is_rejected(world) -> None:  # type: ignore[no-untyped-def]
    from src.tools.base import ToolValidationError

    foreign = _foreign_sample(world)
    intent = _intent(world, ["qc"], [])
    intent["sample_ids"].append(str(foreign.id))
    with pytest.raises(ToolValidationError, match="not in the database"):
        await OrchestratorAgent(_llm(intent)).dispatch_from_chat(
            _say(world, "QC on all samples"), world.db, AsyncMock()
        )
    assert world.db.query(AnalysisRun).count() == 0


async def test_samples_from_two_projects_ask_which_project(world) -> None:  # type: ignore[no-untyped-def]
    second = Project(name="p2", owner="t")  # same principal, different project
    world.db.add(second)
    world.db.flush()
    s2 = Sample(
        project_id=second.id,
        name="P2S",
        sample_type=SampleType.bulk_rnaseq,
        fastq_r1_path="/d/p2.fq",
        is_paired_end=False,
    )
    world.db.add(s2)
    world.db.commit()
    intent = _intent(world, ["qc"], [])
    intent["sample_ids"].append(str(s2.id))
    out = await OrchestratorAgent(_llm(intent)).dispatch_from_chat(
        _say(world, "QC on everything"), world.db, AsyncMock()
    )
    assert out.needs_clarification and out.run_id is None
    assert "different projects" in out.clarification_prompt
