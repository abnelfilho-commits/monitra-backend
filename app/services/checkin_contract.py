"""Descriptive ordinal responses, not a scored or validated instrument."""
CODE = 'BEM_ESTAR_V1'
NAME = 'Check-in de Bem-Estar'
OPTIONS = [('MUITO_RUIM','Muito ruim'),('RUIM','Ruim'),('REGULAR','Regular'),('BOM','Bom'),('MUITO_BOM','Muito bom')]
INTENSITY = [('NENHUMA','Nenhuma'),('POUCA','Pouca'),('MODERADA','Moderada'),('MUITA','Muita'),('EXTREMA','Extrema')]
YES_NO = [('SIM','Sim'),('NAO','Não')]
FIELDS = [
 ('humor','Como você percebe seu humor hoje?', OPTIONS),
 ('ansiedade','Quanta ansiedade ou tensão você percebe hoje?', INTENSITY),
 ('estresse','Quanto estresse você percebe hoje?', INTENSITY),
 ('sono','Como você percebe seu sono?', OPTIONS),
 ('energia','Como você percebe sua energia hoje?', OPTIONS),
 ('funcionamento','Como você percebe sua capacidade de realizar as atividades do dia?', OPTIONS),
 ('trabalho','Como você percebe seu bem-estar em relação ao trabalho?', OPTIONS + [('NAO_SE_APLICA','Não se aplica')]),
 ('evento_relevante','Houve algum evento relevante que gostaria de registrar?', YES_NO),
 ('pedido_ajuda','Você gostaria de receber apoio ou conversar com um profissional?', YES_NO),
 ('evento_descricao','Descrição do evento (opcional)', []),
]
