from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os
import calendar

app = FastAPI(title="API do Dashboard Financeiro - Real com Metas")

# 1. Configuração de CORS para permitir acesso web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URL Supabase (Atenção: como você compartilhou essa senha, é recomendado trocá-la depois no painel do Supabase por segurança)
DATABASE_URL = "postgresql://postgres.pjwaezeuradysckznqdd:34xdHmE91WI4PF2D@aws-0-us-west-2.pooler.supabase.com:5432/postgres"

# -------------------------------------------------------------------
# 2. Conexão e Inicialização do Banco
# -------------------------------------------------------------------
def conectar_banco():
    return psycopg2.connect(DATABASE_URL)

def iniciar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lancamentos (
            id SERIAL PRIMARY KEY,
            tipo TEXT,
            categoria TEXT,
            valor REAL,
            data_emissao DATE,
            status TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metas (
            id SERIAL PRIMARY KEY,
            mes TEXT,
            ano TEXT,
            meta_receita REAL,
            meta_despesa REAL,
            UNIQUE(mes, ano)
        )
    ''')
    
    conn.commit()
    conn.close()

iniciar_banco()

# -------------------------------------------------------------------
# 3. Regras de Entrada (Modelos)
# -------------------------------------------------------------------
class LancamentoNovo(BaseModel):
    tipo: str
    categoria: str
    valor: float
    data_emissao: str
    status: str

class MetaMensal(BaseModel):
    mes: str            
    ano: str            
    meta_receita: float 
    meta_despesa: float 

# -------------------------------------------------------------------
# 4. Rota POST: Salvando Lançamentos
# -------------------------------------------------------------------
@app.post("/api/lancamentos")
def registrar_lancamento(lancamento: LancamentoNovo):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO lancamentos (tipo, categoria, valor, data_emissao, status)
            VALUES (%s, %s, %s, %s, %s)
        ''', (lancamento.tipo, lancamento.categoria, lancamento.valor, lancamento.data_emissao, lancamento.status))
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento salvo!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# 5. Rota POST: Definindo as Metas do Mês
# -------------------------------------------------------------------
@app.post("/api/metas")
def definir_metas(meta: MetaMensal):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO metas (mes, ano, meta_receita, meta_despesa)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (mes, ano) 
            DO UPDATE SET 
                meta_receita = EXCLUDED.meta_receita,
                meta_despesa = EXCLUDED.meta_despesa;
        ''', (meta.mes, meta.ano, meta.meta_receita, meta.meta_despesa))
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": f"Metas de {meta.mes}/{meta.ano} atualizadas!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# 6. Rota GET: O Motor de Cálculo do Dashboard
# -------------------------------------------------------------------
@app.get("/api/dashboard/{ano}/{mes}")
def gerar_resumo_mensal(ano: str, mes: int):
    conn = conectar_banco()
    cursor = conn.cursor()
    
    mes_formatado = f"{mes:02d}"
    
    # 1. Busca os Lançamentos (Agora com EXTRACT do Postgres)
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Pago' THEN valor ELSE 0 END) as receitas_realizadas,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Pago' THEN valor ELSE 0 END) as despesas_realizadas,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Não Pago' THEN valor ELSE 0 END) as contas_a_receber,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Não Pago' THEN valor ELSE 0 END) as contas_a_pagar
        FROM lancamentos
        WHERE EXTRACT(MONTH FROM data_emissao) = %s AND EXTRACT(YEAR FROM data_emissao) = %s
    ''', (mes, ano))
    
    resultado_banco = cursor.fetchone()
    
    total_receitas = resultado_banco[0] if resultado_banco[0] else 0.0
    total_despesas = resultado_banco[1] if resultado_banco[1] else 0.0
    contas_receber = resultado_banco[2] if resultado_banco[2] else 0.0
    contas_pagar = resultado_banco[3] if resultado_banco[3] else 0.0
    
    # 2. Busca as Metas
    cursor.execute('''
        SELECT meta_receita, meta_despesa
        FROM metas
        WHERE mes = %s AND ano = %s
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

# -------------------------------------------------------------------
# 7. Rota GET: Relatório de Fluxo de Caixa Diário
# -------------------------------------------------------------------
@app.get("/api/relatorios/fluxo-diario/{ano}/{mes}")
def gerar_fluxo_diario(ano: str, mes: int):
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # Agora extraímos o dia diretamente com a função do Postgres
    cursor.execute('''
        SELECT 
            EXTRACT(DAY FROM data_emissao) as dia,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Pago' THEN valor ELSE 0 END) as receita,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Pago' THEN valor ELSE 0 END) as despesa,
            SUM(CASE WHEN tipo = 'Receita' AND status = 'Não Pago' THEN valor ELSE 0 END) as receber,
            SUM(CASE WHEN tipo = 'Despesa' AND status = 'Não Pago' THEN valor ELSE 0 END) as pagar
        FROM lancamentos
        WHERE EXTRACT(MONTH FROM data_emissao) = %s AND EXTRACT(YEAR FROM data_emissao) = %s
        GROUP BY dia
        ORDER BY dia
    ''', (mes, ano))
    
    resultados_banco = cursor.fetchall()
    conn.close()
    
    dados_por_dia = {int(linha[0]): linha for linha in resultados_banco}
    
    _, num_dias = calendar.monthrange(int(ano), mes)
    
    fluxo_diario = []
    
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
        "periodo": f"{mes:02d}/{ano}",
        "dias_do_mes": num_dias,
        "fluxo": fluxo_diario
    }

# -------------------------------------------------------------------
# 8. Rota GET: Análise do Plano de Contas (Por Categoria)
# -------------------------------------------------------------------
@app.get("/api/relatorios/analise-contas/{ano}/{mes}/{tipo}")
def gerar_analise_contas(ano: str, mes: int, tipo: str):
    if tipo not in ["Receita", "Despesa"]:
        raise HTTPException(status_code=400, detail="O tipo deve ser 'Receita' ou 'Despesa'.")
        
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # Arrumado para EXTRACT e todos os parâmetros em %s
    cursor.execute('''
        SELECT 
            categoria,
            SUM(valor) as total_categoria
        FROM lancamentos
        WHERE EXTRACT(MONTH FROM data_emissao) = %s 
          AND EXTRACT(YEAR FROM data_emissao) = %s 
          AND tipo = %s 
          AND status = 'Pago'
        GROUP BY categoria
        ORDER BY total_categoria DESC
    ''', (mes, ano, tipo))
    
    resultados_banco = cursor.fetchall()
    
    cursor.execute('''
        SELECT SUM(valor)
        FROM lancamentos
        WHERE EXTRACT(MONTH FROM data_emissao) = %s 
          AND EXTRACT(YEAR FROM data_emissao) = %s 
          AND tipo = %s 
          AND status = 'Pago'
    ''', (mes, ano, tipo))
    
    total_geral_mes = cursor.fetchone()[0]
    total_geral_mes = total_geral_mes if total_geral_mes else 0.0
    
    conn.close()
    
    analise = []
    for linha in resultados_banco:
        nome_categoria = linha[0]
        valor_categoria = linha[1]
        percentual = (valor_categoria / total_geral_mes * 100) if total_geral_mes > 0 else 0.0
        
        analise.append({
            "categoria": nome_categoria,
            "valor_absoluto": round(valor_categoria, 2),
            "percentual_do_total": round(percentual, 2)
        })
        
    return {
        "periodo": f"{mes:02d}/{ano}",
        "tipo_analise": tipo,
        "total_geral": round(total_geral_mes, 2),
        "detalhamento": analise
    }

# -------------------------------------------------------------------
# 9. Rota GET: Listar todos os lançamentos para a tabela
# -------------------------------------------------------------------
@app.get("/api/lancamentos")
def listar_lancamentos():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute('SELECT id, data_emissao, tipo, categoria, valor, status FROM lancamentos ORDER BY data_emissao DESC')
    linhas = cursor.fetchall()
    conn.close()
    
    lista = []
    for l in linhas:
        # Pydantic/FastAPI transforma o objeto de data automaticamente para string
        lista.append({
            "id": l[0], "data_emissao": l[1], "tipo": l[2], 
            "categoria": l[3], "valor": l[4], "status": l[5]
        })
    return lista

# -------------------------------------------------------------------
# 10. Rota PUT: Atualizar (Editar) um Lançamento Existente
# -------------------------------------------------------------------
@app.put("/api/lancamentos/{item_id}")
def atualizar_lancamento(item_id: int, lancamento: LancamentoNovo):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE lancamentos
            SET tipo = %s, categoria = %s, valor = %s, data_emissao = %s, status = %s
            WHERE id = %s
        ''', (lancamento.tipo, lancamento.categoria, lancamento.valor, lancamento.data_emissao, lancamento.status, item_id))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Lançamento não encontrado para edição.")
            
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento atualizado!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# 11. Rota DELETE: Excluir um Lançamento Permanentemente
# -------------------------------------------------------------------
@app.delete("/api/lancamentos/{item_id}")
def excluir_lancamento(item_id: int):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        
        # Arrumado: trocado '?' por '%s'
        cursor.execute('DELETE FROM lancamentos WHERE id = %s', (item_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            raise HTTPException(status_code=404, detail="Lançamento não encontrado para exclusão.")
            
        conn.commit()
        conn.close()
        return {"sucesso": True, "mensagem": "Lançamento excluído com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))