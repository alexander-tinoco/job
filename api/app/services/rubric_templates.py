"""Starting rubrics by role type.

HR at a small business rarely writes a good rubric from a blank page, and a bad
rubric produces a bad screen that gets blamed on the AI (plan §4.2). These are
worked examples meant to be edited, not used verbatim.
"""

from pydantic import BaseModel

from app.schemas.openings import CriterionIn


class RubricTemplate(BaseModel):
    key: str
    label: str
    criteria: list[CriterionIn]


TEMPLATES: list[RubricTemplate] = [
    RubricTemplate(
        key="software_engineer",
        label="Software engineer",
        criteria=[
            CriterionIn(
                name="Core language depth",
                description=(
                    "Years and depth in the stack's main language. Good: 'led a Python "
                    "service handling 2k req/s'. Bad: 'knows Python'."
                ),
                weight=35,
                mandatory=True,
            ),
            CriterionIn(
                name="System design",
                description=(
                    "Evidence of designing, not just implementing. Look for migrations, "
                    "trade-offs made explicit, or ownership of an architecture."
                ),
                weight=25,
            ),
            CriterionIn(
                name="Data and persistence",
                description="Relational modelling, query tuning, or handling data at scale.",
                weight=20,
            ),
            CriterionIn(
                name="Delivery track record",
                description=(
                    "Shipped work with measurable outcomes. Prefer 'cut checkout errors "
                    "40%' over a list of technologies."
                ),
                weight=20,
            ),
        ],
    ),
    RubricTemplate(
        key="sales",
        label="Sales",
        criteria=[
            CriterionIn(
                name="Quota attainment",
                description="Concrete numbers against a stated target, not adjectives.",
                weight=35,
                mandatory=True,
            ),
            CriterionIn(
                name="Segment fit",
                description="Experience selling to a comparable buyer, deal size and cycle.",
                weight=30,
            ),
            CriterionIn(
                name="Pipeline ownership",
                description="Prospecting done personally versus inherited from marketing.",
                weight=20,
            ),
            CriterionIn(
                name="Tenure stability",
                description="Long enough in each role to have closed a full cycle.",
                weight=15,
            ),
        ],
    ),
    RubricTemplate(
        key="administration",
        label="Administration",
        criteria=[
            CriterionIn(
                name="Process ownership",
                description="Ran a recurring process end to end without supervision.",
                weight=35,
                mandatory=True,
            ),
            CriterionIn(
                name="Tooling",
                description="Depth in the specific tools the role uses daily.",
                weight=30,
            ),
            CriterionIn(
                name="Accuracy under volume",
                description="Evidence of handling volume without errors piling up.",
                weight=20,
            ),
            CriterionIn(
                name="Written communication",
                description="The résumé itself is a sample. Judge clarity and structure.",
                weight=15,
            ),
        ],
    ),
    RubricTemplate(
        key="operations",
        label="Operations",
        criteria=[
            CriterionIn(
                name="Operational ownership",
                description="Responsible for an outcome, not only for executing steps.",
                weight=35,
                mandatory=True,
            ),
            CriterionIn(
                name="Measurable improvement",
                description="Reduced a cost, a cycle time or an error rate, with the number.",
                weight=30,
            ),
            CriterionIn(
                name="Coordination",
                description="Worked across teams or suppliers rather than in isolation.",
                weight=20,
            ),
            CriterionIn(
                name="Domain familiarity",
                description="Comparable industry, scale or regulatory environment.",
                weight=15,
            ),
        ],
    ),
]

BY_KEY: dict[str, RubricTemplate] = {t.key: t for t in TEMPLATES}
