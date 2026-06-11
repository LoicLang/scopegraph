from core.runtime.brief import QA, ProjectBrief


def test_text_concatenates_description_and_qa() -> None:
    brief = ProjectBrief(description="Paiement en 3 fois dans l'app mobile.")
    brief.qa.append(QA(question="Le périmètre inclut-il « monetique » ?", answer="oui"))
    text = brief.text()
    assert "Paiement en 3 fois" in text
    assert "monetique" in text  # the question's vocabulary enriches the query
    assert "oui" in text


def test_defaults_are_empty() -> None:
    brief = ProjectBrief(description="x")
    assert brief.qa == []
    assert brief.domains == []
    assert brief.excluded_domains == []
