from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware # 1. Importe esta linha
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="API do Dashboard Financeiro - Real com Metas")

# 2. Adicione este bloco de configuração logo após criar o 'app'
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # O asterisco permite que qualquer HTML acesse sua API
    allow_credentials=True,
    allow_methods=["*"], # Permite enviar (POST) e receber (GET)
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# 1. Configuração do Banco de Dados (Agora com tabela de Metas)
# -------------------------------------------------------------------
def iniciar_banco():
    conn = sqlite3.connect('meu_financeiro.db')
    cursor = conn.cursor()
    
    # Tabela de Lançamentos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            categoria TEXT,
            valor REAL,
            data_emissao DATE,
            status TEXT
        )
    ''')
    
    # Nova Tabela de Metas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes TEXT,
            ano TEXT,
            meta_receita REAL,
            meta_despesa REAL,
            UNIQUE(mes, ano) -- Garante que só teremos uma meta por mês/ano
        )
    ''')
    
    conn.commit()
    conn.close()

iniciar_banco()

# -------------------------------------------------------------------
# 2. Regras de Entrada (Modelos)
# -------------------------------------------------------------------
class LancamentoNovo(BaseModel):
    tipo: str
    categoria: str
    valor: float
    data_emissao: str
    status: str

class MetaMensal(BaseModel):
    mes: str            # Ex: "03"
    ano: str            # Ex: "2026"
    meta_receita: float # Ex: 13500.00
    meta_despesa: float # Ex: 10000.00

# -------------------------------------------------------------------
# 3. Rota POST: Salvando Lançamentos
# -------------------------------------------------------------------
@app.post("/api/lancamentos")
def registrar_lancamento(lancamento: LancamentoNovo):
    try:
        conn = sqlite3.connect('meu_financeiro.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO lancamentos (tipo, categoria, valor, data_emissao, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (lancamento.tipo, lancamento.categoria, lancamento.valor, lancamento.data_emissao, lancamento.status))
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento salvo!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# 4. Nova Rota POST: Definindo as Metas do Mês
# -------------------------------------------------------------------
@app.post("/api/metas")
def definir_metas(meta: MetaMensal):
    try:
        conn = sqlite3.connect('meu_financeiro.db')
        cursor = conn.cursor()
        
        # O REPLACE INTO atualiza a meta se já existir uma para aquele mês/ano, ou cria uma nova
        cursor.execute('''
            REPLACE INTO metas (mes, ano, meta_receita, meta_despesa)
            VALUES (?, ?, ?, ?)
        ''', (meta.mes, meta.ano, meta.meta_receita, meta.meta_despesa))
        
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": f"Metas de {meta.mes}/{meta.ano} atualizadas!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# 5. Rota GET: O Motor de Cálculo do Dashboard (Agora com Pendências)
# -------------------------------------------------------------------
@app.get("/api/dashboard/{ano}/{mes}")
def gerar_resumo_mensal(ano: str, mes: int):
    conn = sqlite3.connect('meu_financeiro.db')
    cursor = conn.cursor()
    
    mes_formatado = f"{mes:02d}"
    
    # 1. Busca os Lançamentos: Separando Pagos e Não Pagos na mesma consulta
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Pago' THEN valor ELSE 0 END) as receitas_realizadas,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Pago' THEN valor ELSE 0 END) as despesas_realizadas,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Não Pago' THEN valor ELSE 0 END) as contas_a_receber,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Não Pago' THEN valor ELSE 0 END) as contas_a_pagar
        FROM lancamentos
        WHERE strftime('%m', data_emissao) = ? AND strftime('%Y', data_emissao) = ?
    ''', (mes_formatado, ano))
    
    resultado_banco = cursor.fetchone()
    
    # Prevenindo valores nulos caso o banco esteja vazio
    total_receitas = resultado_banco[0] if resultado_banco[0] else 0.0
    total_despesas = resultado_banco[1] if resultado_banco[1] else 0.0
    contas_receber = resultado_banco[2] if resultado_banco[2] else 0.0
    contas_pagar = resultado_banco[3] if resultado_banco[3] else 0.0
    
    # 2. Busca as Metas
    cursor.execute('''
        SELECT meta_receita, meta_despesa
        FROM metas
        WHERE mes = ? AND ano = ?
    ''', (mes_formatado, ano))
    
    resultado_metas = cursor.fetchone()
    conn.close()
    
    meta_receita = resultado_metas[0] if resultado_metas else 0.0
    meta_despesa = resultado_metas[1] if resultado_metas else 0.0
    
    # 3. Cálculos de Performance
    resultado_caixa = total_receitas - total_despesas
    lucratividade = (resultado_caixa / total_receitas * 100) if total_receitas > 0 else 0.0
    necessidade_caixa = contas_pagar - contas_receber - resultado_caixa
    
    return {
        "periodo": f"{mes_formatado}/{ano}",
        "financeiro_real": {
            "receitas_pagas": round(total_receitas, 2),
            "despesas_pagas": round(total_despesas, 2),
            "saldo_resultado": round(resultado_caixa, 2),
            "lucratividade_percentual": round(lucratividade, 2)
        },
        "pendencias": {
            "contas_a_receber": round(contas_receber, 2),
            "contas_a_pagar": round(contas_pagar, 2),
            "necessidade_de_caixa": round(necessidade_caixa, 2)
        },
        "metas": {
            "meta_receita": round(meta_receita, 2),
            "meta_despesa": round(meta_despesa, 2)
        }
    }

import calendar

# -------------------------------------------------------------------
# 6. Rota GET: Relatório de Fluxo de Caixa Diário
# -------------------------------------------------------------------
@app.get("/api/relatorios/fluxo-diario/{ano}/{mes}")
def gerar_fluxo_diario(ano: str, mes: int):
    conn = sqlite3.connect('meu_financeiro.db')
    cursor = conn.cursor()
    
    mes_formatado = f"{mes:02d}"
    
    # O "GROUP BY dia" é a mágica que agrupa os lançamentos de cada dia específico
    cursor.execute('''
        SELECT 
            CAST(strftime('%d', data_emissao) AS INTEGER) as dia,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Pago' THEN valor ELSE 0 END) as receita,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Pago' THEN valor ELSE 0 END) as despesa,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Não Pago' THEN valor ELSE 0 END) as receber,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Não Pago' THEN valor ELSE 0 END) as pagar
        FROM lancamentos
        WHERE strftime('%m', data_emissao) = ? AND strftime('%Y', data_emissao) = ?
        GROUP BY dia
        ORDER BY dia
    ''', (mes_formatado, ano))
    
    resultados_banco = cursor.fetchall()
    conn.close()
    
    # Transforma o resultado do banco num dicionário para facilitar a busca
    dados_por_dia = {linha[0]: linha for linha in resultados_banco}
    
    # Descobre quantos dias tem o mês escolhido (ex: Fevereiro de 2026 tem 28 dias)
    _, num_dias = calendar.monthrange(int(ano), mes)
    
    fluxo_diario = []
    
    # Cria uma lista completa com todos os dias do mês (mesmo os dias sem movimentação)
    for dia in range(1, num_dias + 1):
        if dia in dados_por_dia:
            _, receita, despesa, receber, pagar = dados_por_dia[dia]
        else:
            receita = despesa = receber = pagar = 0.0
            
        resultado_dia = receita - despesa
        necessidade_caixa = pagar - receber
            
        fluxo_diario.append({
            "dia": dia,
            "receita": round(receita, 2),
            "despesa": round(despesa, 2),
            "resultado": round(resultado_dia, 2),
            "contas_a_receber": round(receber, 2),
            "contas_a_pagar": round(pagar, 2),
            "necessidade_de_caixa": round(necessidade_caixa, 2)
        })
        
    return {
        "periodo": f"{mes_formatado}/{ano}",
        "dias_do_mes": num_dias,
        "fluxo": fluxo_diario
    }

# -------------------------------------------------------------------
# 7. Rota GET: Análise do Plano de Contas (Por Categoria)
# -------------------------------------------------------------------
@app.get("/api/relatorios/analise-contas/{ano}/{mes}/{tipo}")
def gerar_analise_contas(ano: str, mes: int, tipo: str):
    # O "tipo" na URL deve ser "Receita" ou "Despesa"
    if tipo not in ["Receita", "Despesa"]:
        raise HTTPException(status_code=400, detail="O tipo deve ser 'Receita' ou 'Despesa'.")
        
    conn = sqlite3.connect('meu_financeiro.db')
    cursor = conn.cursor()
    
    mes_formatado = f"{mes:02d}"
    
    # Busca o total agrupado por Categoria (Ex: "Marketing: R$ 2300")
    cursor.execute('''
        SELECT 
            categoria,
            SUM(valor) as total_categoria
        FROM lancamentos
        WHERE strftime('%m', data_emissao) = ? 
          AND strftime('%Y', data_emissao) = ? 
          AND tipo = ? 
          AND status = 'Pago'
        GROUP BY categoria
        ORDER BY total_categoria DESC
    ''', (mes_formatado, ano, tipo))
    
    resultados_banco = cursor.fetchall()
    
    # Vamos buscar também o total geral desse tipo no mês para calcular as porcentagens
    cursor.execute('''
        SELECT SUM(valor)
        FROM lancamentos
        WHERE strftime('%m', data_emissao) = ? 
          AND strftime('%Y', data_emissao) = ? 
          AND tipo = ? 
          AND status = 'Pago'
    ''', (mes_formatado, ano, tipo))
    
    total_geral_mes = cursor.fetchone()[0]
    total_geral_mes = total_geral_mes if total_geral_mes else 0.0
    
    conn.close()
    
    # Montando a lista final com os valores absolutos e os percentuais (para o gráfico de rosca)
    analise = []
    for linha in resultados_banco:
        nome_categoria = linha[0]
        valor_categoria = linha[1]
        
        # Calcula a fatia (porcentagem) dessa categoria no total
        percentual = (valor_categoria / total_geral_mes * 100) if total_geral_mes > 0 else 0.0
        
        analise.append({
            "categoria": nome_categoria,
            "valor_absoluto": round(valor_categoria, 2),
            "percentual_do_total": round(percentual, 2)
        })
        
    return {
        "periodo": f"{mes_formatado}/{ano}",
        "tipo_analise": tipo,
        "total_geral": round(total_geral_mes, 2),
        "detalhamento": analise
    }

# -------------------------------------------------------------------
# Nova Rota GET: Listar todos os lançamentos para a tabela
# -------------------------------------------------------------------
@app.get("/api/lancamentos")
def listar_lancamentos():
    conn = sqlite3.connect('meu_financeiro.db')
    cursor = conn.cursor()
    # Busca todos os lançamentos ordenados do mais recente para o mais antigo
    cursor.execute('SELECT id, data_emissao, tipo, categoria, valor, status FROM lancamentos ORDER BY data_emissao DESC')
    linhas = cursor.fetchall()
    conn.close()
    
    # Transforma em uma lista amigável para a tela web ler
    lista = []
    for l in linhas:
        lista.append({
            "id": l[0], "data_emissao": l[1], "tipo": l[2], 
            "categoria": l[3], "valor": l[4], "status": l[5]
        })
    return lista

# -------------------------------------------------------------------
# Rota PUT: Atualizar (Editar) um Lançamento Existente
# -------------------------------------------------------------------
@app.put("/api/lancamentos/{item_id}")
def atualizar_lancamento(item_id: int, lancamento: LancamentoNovo):
    try:
        conn = sqlite3.connect('meu_financeiro.db')
        cursor = conn.cursor()
        
        # O UPDATE substitui os dados antigos pelos novos usando o ID como alvo
        cursor.execute('''
            UPDATE lancamentos
            SET tipo = ?, categoria = ?, valor = ?, data_emissao = ?, status = ?
            WHERE id = ?
        ''', (lancamento.tipo, lancamento.categoria, lancamento.valor, lancamento.data_emissao, lancamento.status, item_id))
        
        # rowcount verifica se alguma linha foi realmente alterada
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Lançamento não encontrado para edição.")
            
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento atualizado com sucesso!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar: {str(e)}")


# -------------------------------------------------------------------
# Rota DELETE: Excluir um Lançamento Permanentemente
# -------------------------------------------------------------------
@app.delete("/api/lancamentos/{item_id}")
def excluir_lancamento(item_id: int):
    try:
        conn = sqlite3.connect('meu_financeiro.db')
        cursor = conn.cursor()
        
        # O DELETE apaga a linha inteira do banco de dados baseada no ID
        cursor.execute('DELETE FROM lancamentos WHERE id = ?', (item_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Lançamento não encontrado para exclusão.")
            
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento excluído com sucesso!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao excluir: {str(e)}")