from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, delete, select

from src.models.puzzle import (
    Character,
    CharacterStatus,
    ConfidenceLevel,
    Deduction,
    DeductionStatus,
    EntityKind,
    Fact,
    Hint,
    HintScope,
    HintType,
    IgnoredEntity,
    Location,
    Project,
    ProjectSummary,
    Rejection,
    Script,
    ScriptMetadata,
    SourceType,
    TimeSlot,
)
from src.storage.sqlite_schema import (
    CharacterTable,
    DeductionTable,
    FactTable,
    HintTable,
    IgnoredEntityTable,
    LocationTable,
    ProjectTable,
    RejectionTable,
    ScriptTable,
    TimeSlotTable,
)


class SQLiteStore:
    """SQLite + SQLModel storage for core project entities.

    This is additive foundation only and does not change default app behavior.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent.parent / "data" / "projects.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)

    def create_schema(self) -> None:
        SQLModel.metadata.create_all(self.engine)

    def session(self) -> Session:
        self.create_schema()
        return Session(self.engine)

    def list_projects(self) -> list[ProjectSummary]:
        self.create_schema()
        with self.session() as session:
            rows = session.exec(select(ProjectTable).order_by(ProjectTable.updated_at.desc())).all()
            return [
                ProjectSummary(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    character_count=row.character_count,
                    location_count=row.location_count,
                    script_count=row.script_count,
                    fact_count=row.fact_count,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def load_project(self, project_id: str) -> Project:
        self.create_schema()
        with self.session() as session:
            project_row = session.get(ProjectTable, project_id)
            if project_row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")

            characters = session.exec(
                select(CharacterTable).where(CharacterTable.project_id == project_id)
            ).all()
            locations = session.exec(
                select(LocationTable).where(LocationTable.project_id == project_id)
            ).all()
            time_slots = session.exec(
                select(TimeSlotTable)
                .where(TimeSlotTable.project_id == project_id)
                .order_by(TimeSlotTable.sort_order)
            ).all()
            scripts = session.exec(
                select(ScriptTable).where(ScriptTable.project_id == project_id)
            ).all()
            facts = session.exec(select(FactTable).where(FactTable.project_id == project_id)).all()
            deductions = session.exec(
                select(DeductionTable).where(DeductionTable.project_id == project_id)
            ).all()
            rejections = session.exec(
                select(RejectionTable).where(RejectionTable.project_id == project_id)
            ).all()
            hints = session.exec(select(HintTable).where(HintTable.project_id == project_id)).all()
            ignored_entities = session.exec(
                select(IgnoredEntityTable).where(IgnoredEntityTable.project_id == project_id)
            ).all()

        return Project(
            id=project_row.id,
            name=project_row.name,
            description=project_row.description,
            created_at=project_row.created_at,
            updated_at=project_row.updated_at,
            characters=[
                Character(
                    id=row.id,
                    name=row.name,
                    aliases=row.aliases or [],
                    description=row.description,
                    status=CharacterStatus(row.status),
                    discovered_in_script_id=row.discovered_in_script_id,
                    created_at=row.created_at,
                )
                for row in characters
            ],
            locations=[
                Location(
                    id=row.id,
                    name=row.name,
                    aliases=row.aliases or [],
                    description=row.description,
                    discovered_in_script_id=row.discovered_in_script_id,
                    created_at=row.created_at,
                )
                for row in locations
            ],
            time_slots=[
                TimeSlot(
                    id=row.id,
                    label=row.label,
                    description=row.description,
                    sort_order=row.sort_order,
                )
                for row in time_slots
            ],
            scripts=[
                Script(
                    id=row.id,
                    title=row.title,
                    raw_text=row.raw_text,
                    metadata=ScriptMetadata.model_validate(row.metadata_json or {}),
                    analysis_result=row.analysis_result,
                    added_at=row.added_at,
                )
                for row in scripts
            ],
            facts=[
                Fact(
                    id=row.id,
                    character_id=row.character_id,
                    location_id=row.location_id,
                    time_slot=row.time_slot,
                    source_type=SourceType(row.source_type),
                    source_evidence=row.source_evidence,
                    source_script_ids=row.source_script_ids or [],
                    from_deduction_id=row.from_deduction_id,
                    confirmed_at=row.confirmed_at,
                )
                for row in facts
            ],
            deductions=[
                Deduction(
                    id=row.id,
                    character_id=row.character_id,
                    location_id=row.location_id,
                    time_slot=row.time_slot,
                    confidence=ConfidenceLevel(row.confidence),
                    reasoning=row.reasoning,
                    supporting_script_ids=row.supporting_script_ids or [],
                    depends_on_fact_ids=row.depends_on_fact_ids or [],
                    status=DeductionStatus(row.status),
                    batch_id=row.batch_id,
                    created_at=row.created_at,
                    resolved_at=row.resolved_at,
                )
                for row in deductions
            ],
            rejections=[
                Rejection(
                    id=row.id,
                    character_id=row.character_id,
                    location_id=row.location_id,
                    time_slot=row.time_slot,
                    reason=row.reason,
                    from_deduction_id=row.from_deduction_id,
                    rejected_at=row.rejected_at,
                )
                for row in rejections
            ],
            hints=[
                Hint(
                    id=row.id,
                    type=HintType(row.type),
                    content=row.content,
                    applies_to=HintScope.model_validate(row.applies_to_json or {}),
                    created_at=row.created_at,
                )
                for row in hints
            ],
            ignored_entities=[
                IgnoredEntity(
                    id=row.id,
                    kind=EntityKind(row.kind),
                    name=row.name,
                    created_at=row.created_at,
                )
                for row in ignored_entities
            ],
        )

    def save_project(self, project: Project) -> None:
        self.create_schema()
        with self.session() as session:
            self._delete_project_records(session, project.id)
            self._persist_project_records(session, project)
            session.commit()

    def create_project(
        self,
        name: str,
        description: str | None = None,
        time_slots: list[str] | None = None,
    ) -> Project:
        project = Project(name=name, description=description, time_slots=time_slots or [])
        self.save_project(project)
        return project

    def import_project_from_json(self, json_path: str | Path) -> Project:
        source_path = Path(json_path)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"无法导入 JSON 项目：文件不存在 - {source_path}")

        try:
            raw_json = source_path.read_text(encoding="utf-8")
            project = Project.model_validate_json(raw_json)
        except (OSError, UnicodeDecodeError, ValidationError) as exc:
            raise ValueError(f"无法导入 JSON 项目：{source_path}") from exc

        self.create_schema()
        try:
            with self.session() as session:
                self._delete_project_records(session, project.id)
                self._persist_project_records(session, project)
                session.commit()
        except Exception as exc:
            raise ValueError(f"无法导入 JSON 项目：{source_path}") from exc

        return project

    def delete_project(self, project_id: str) -> None:
        self.create_schema()
        with self.session() as session:
            project_row = session.get(ProjectTable, project_id)
            if project_row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            self._delete_project_records(session, project_id)
            session.commit()

    def _delete_project_records(self, session: Session, project_id: str) -> None:
        session.exec(delete(CharacterTable).where(CharacterTable.project_id == project_id))
        session.exec(delete(LocationTable).where(LocationTable.project_id == project_id))
        session.exec(delete(TimeSlotTable).where(TimeSlotTable.project_id == project_id))
        session.exec(delete(ScriptTable).where(ScriptTable.project_id == project_id))
        session.exec(delete(FactTable).where(FactTable.project_id == project_id))
        session.exec(delete(DeductionTable).where(DeductionTable.project_id == project_id))
        session.exec(delete(RejectionTable).where(RejectionTable.project_id == project_id))
        session.exec(delete(HintTable).where(HintTable.project_id == project_id))
        session.exec(delete(IgnoredEntityTable).where(IgnoredEntityTable.project_id == project_id))
        session.exec(delete(ProjectTable).where(ProjectTable.id == project_id))

    def _persist_project_records(self, session: Session, project: Project) -> None:
        session.add(
            ProjectTable(
                id=project.id,
                name=project.name,
                description=project.description,
                created_at=project.created_at,
                updated_at=project.updated_at,
                character_count=len(project.characters),
                location_count=len(project.locations),
                script_count=len(project.scripts),
                fact_count=len(project.facts),
            )
        )
        session.add_all(
            CharacterTable(
                id=row.id,
                project_id=project.id,
                name=row.name,
                aliases=row.aliases,
                description=row.description,
                status=row.status.value,
                discovered_in_script_id=row.discovered_in_script_id,
                created_at=row.created_at,
            )
            for row in project.characters
        )
        session.add_all(
            LocationTable(
                id=row.id,
                project_id=project.id,
                name=row.name,
                aliases=row.aliases,
                description=row.description,
                discovered_in_script_id=row.discovered_in_script_id,
                created_at=row.created_at,
            )
            for row in project.locations
        )
        session.add_all(
            TimeSlotTable(
                id=row.id,
                project_id=project.id,
                label=row.label,
                description=row.description,
                sort_order=row.sort_order,
            )
            for row in project.time_slots
        )
        session.add_all(
            ScriptTable(
                id=row.id,
                project_id=project.id,
                title=row.title,
                raw_text=row.raw_text,
                metadata_json=row.metadata.model_dump(),
                analysis_result=row.analysis_result,
                added_at=row.added_at,
            )
            for row in project.scripts
        )
        session.add_all(
            FactTable(
                id=row.id,
                project_id=project.id,
                character_id=row.character_id,
                location_id=row.location_id,
                time_slot=row.time_slot,
                source_type=row.source_type.value,
                source_evidence=row.source_evidence,
                source_script_ids=row.source_script_ids,
                from_deduction_id=row.from_deduction_id,
                confirmed_at=row.confirmed_at,
            )
            for row in project.facts
        )
        session.add_all(
            DeductionTable(
                id=row.id,
                project_id=project.id,
                character_id=row.character_id,
                location_id=row.location_id,
                time_slot=row.time_slot,
                confidence=row.confidence.value,
                reasoning=row.reasoning,
                supporting_script_ids=row.supporting_script_ids,
                depends_on_fact_ids=row.depends_on_fact_ids,
                status=row.status.value,
                batch_id=row.batch_id,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
            )
            for row in project.deductions
        )
        session.add_all(
            RejectionTable(
                id=row.id,
                project_id=project.id,
                character_id=row.character_id,
                location_id=row.location_id,
                time_slot=row.time_slot,
                reason=row.reason,
                from_deduction_id=row.from_deduction_id,
                rejected_at=row.rejected_at,
            )
            for row in project.rejections
        )
        session.add_all(
            HintTable(
                id=row.id,
                project_id=project.id,
                type=row.type.value,
                content=row.content,
                applies_to_json=row.applies_to.model_dump(),
                created_at=row.created_at,
            )
            for row in project.hints
        )
        session.add_all(
            IgnoredEntityTable(
                id=row.id,
                project_id=project.id,
                kind=row.kind.value,
                name=row.name,
                created_at=row.created_at,
            )
            for row in project.ignored_entities
        )
