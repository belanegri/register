from pathlib import Path

base = Path(__file__).resolve().parents[1]
def editar(nome, antes, depois):
    arquivo = base / nome
    texto = arquivo.read_text(encoding='utf-8')
    assert antes in texto, nome + ': trecho não encontrado'
    arquivo.write_text(texto.replace(antes, depois), encoding='utf-8')

novo = base / 'templates/comercial/contas_profissional.html'
(base / 'templates/comercial/contas.html').write_text(novo.read_text(encoding='utf-8'), encoding='utf-8')
novo.unlink()
editar('templates/comercial/conta.html', '<h1>Conta #{{ conta.pk }} — {{ conta.descricao }}</h1>', '<div class="page-heading"><div><h1>{{ conta.codigo }} · {{ conta.descricao }}</h1><p>Cliente, vencimentos e histórico financeiro.</p></div><a class="btn btn-outline-secondary" href="{% url \'comercial:contas\' %}">Voltar às contas</a></div>')
editar('templates/comercial/conta.html', '<h2>Histórico de recebimentos</h2>', '{% include \'comercial/conta_parcelas.html\' %}<div class="d-flex flex-wrap gap-2 mb-3"><a class="btn btn-outline-secondary" target="_blank" rel="noopener" href="{% url \'comercial:conta_imprimir\' conta.pk %}">Imprimir</a>{% if perms.comercial.change_contareceber and not conta.cancelada and not conta.valor_recebido %}<a class="btn btn-outline-primary" href="{% url \'comercial:conta_parcelamento\' conta.pk %}">Organizar parcelamento</a>{% endif %}</div><h2>Histórico de recebimentos</h2><div class="table-responsive">')
editar('templates/comercial/conta.html', '</table>', '</table></div>')
editar('templates/comercial/conta.html', '<h2>Registrar recebimento</h2>', '<h2 id="recebimento">Confirmar pagamento / recebimento</h2>')
editar('templates/contas/lista.html', "{% extends 'base.html' %}", "{% extends 'base.html' %}{% load static %}")
editar('templates/contas/lista.html', '{% block content %}', '{% block content %}<link rel="stylesheet" href="{% static \'css/financeiro.css\' %}"><div class="financeiro-lista">')
editar('templates/contas/lista.html', '<th>Situação</th>', '<th>Situação</th><th aria-label="Ações"></th>')
editar('templates/contas/lista.html', '</span></td></tr>', '</span></td><td>{% include \'contas/acoes.html\' %}</td></tr>')
editar('templates/contas/lista.html', 'colspan="8"', 'colspan="9"')
editar('templates/contas/lista.html', '{% endblock %}', '{% include \'contas/previas.html\' %}</div>{% endblock %}')
for antes, depois in [('<td>{{ conta.fornecedor }}', '<td data-label="Fornecedor">{{ conta.fornecedor }}'),
    ('<td>{{ conta.get_tipo_conta_display', '<td data-label="Tipo">{{ conta.get_tipo_conta_display'),
    ('<td>{{ conta.forma_prevista', '<td data-label="Forma de pagamento">{{ conta.forma_prevista'),
    ('<td>{{ conta.vencimento', '<td data-label="Vencimento">{{ conta.vencimento'),
    ('<td>{{ conta.data_programada', '<td data-label="Programado">{{ conta.data_programada'),
    ('<td class="text-nowrap">', '<td data-label="Valor" class="text-nowrap">'),
    ('<td><span', '<td data-label="Situação"><span')]:
    editar('templates/contas/lista.html', antes, depois)
editar('static/js/conta-formulario.js', "mode !== 'recorrente';", "mode === 'unica';")
editar('static/js/conta-formulario.js', 'parcelas mensais', 'parcelas na frequência escolhida')
editar('static/js/conta-formulario.js', "mode === 'parcelada'\n              ? 'mensal'\n              : frequenciaCampo.value", "frequenciaCampo.value || 'mensal'")
editar('static/js/conta-formulario.js', "if (frequency === 'semanal')", "if (['semanal', 'quinzenal', 'dias'].includes(frequency))")
editar('static/js/conta-formulario.js', 'day + index * 7', "day + index * (frequency === 'semanal' ? 7 : frequency === 'quinzenal' ? 15 : Number(el('intervalo_dias')?.value || 30))")
