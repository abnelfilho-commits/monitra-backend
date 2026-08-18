"""
Narrative Builder.

Responsável por construir narrativas institucionais
de forma padronizada.
"""
from typing import Optional

class NarrativeBuilder:
    """
    Constrói textos institucionais do Report Engine.
    """
    def __init__(self):
        self._paragraphs = []
        self._current = []

    def add(self, sentence: Optional[str]):
        """
        Adiciona uma frase ao texto.

        Ignora valores vazios.
        """

        if sentence:
            sentence = sentence.strip()

            if sentence:
                self._current.append(sentence)

        return self

    def add_if(
        self,
        condition: bool,
        sentence: str,
    ):
        """
        Adiciona uma frase somente quando
        a condição for verdadeira.
        """

        if condition:
            self.add(sentence)

        return self
    
    def add_if_value(
        self,
        value,
        formatter,
    ):
        """
        Adiciona uma frase quando existir
        um valor.

        formatter recebe o valor encontrado.
        """

        if value is not None:
            self.add(
                formatter(value)
            )

        return self

    def paragraph(self):
        """
        Finaliza o parágrafo atual.
        """

        if self._current:
            self._paragraphs.append(
                " ".join(self._current)
            )
            self._current = []

        return self

    def build(self) -> str:
        """
        Retorna o texto final em parágrafos.
        """

        self.paragraph()

        return "\n\n".join(
            self._paragraphs
        )

    def clear(self):
        """
        Limpa todo o conteúdo acumulado.
        """

        self._paragraphs.clear()
        self._current.clear()

        return self