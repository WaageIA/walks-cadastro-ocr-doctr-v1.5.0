

import io
import json
import os
import re
from datetime import datetime
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

# Doctr imports
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

# Carrega vari
veis de ambiente do arquivo .env
load_dotenv()

# --- Configura
es da LLM ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_API_URL = "https://api.openai.com/v1/chat/completions"
LLM_MODEL = "gpt-4o-mini"

# Prompt para a LLM (ajustado para focar apenas na extra
o de campos brutos)
LLM_PROMPT_TEMPLATE = """
# Prompt para Convers
o de String para JSON Estruturado
Sua 
ica fun
o 
 converter uma string de entrada (`{raw_text_input}`) para um objeto JSON estruturado, seguindo as regras e o modelo abaixo. Responda apenas com o JSON final ou com a mensagem de erro.

## 1. Mapeamento de Campos
Use esta tabela para mapear os campos do texto para o JSON:
| Texto de Entrada | Chave JSON Final |
|------------------|------------------|
| Nome Completo | `nome_completo` |
| Data de Nascimento | `data_nascimento` |
| CPF | `cpf` |
| Raz
o Social | `empresa` |
| CNPJ | `cnpj` |
| Nome Fantasia | `nome_comprovante` |
| CEP | `cep` |
| Complemento | `complemento` |

## 2. Regras de Processamento
- **Valores Nulos**: Se o valor na entrada for `[ILEG
VEL]`, `[N
O ENCONTRADO]` ou `[N
O APLIC
VEL]`, o campo correspondente no JSON final dever
 ser `null`.
- **Limpeza**: Remova todas as tags (`[...]`) dos valores antes de inseri-los no JSON.
- **Erro**: Se a entrada n
o contiver o padr
o `Chave: Valor`, retorne a string: `Erro 0001. Padr
o execu
o. TESTE. Erro ao Ler imagem do formul
rio, envie novamente por favor.`

## 3. Estrutura de Sa
da Obrigat
ria (apenas campos brutos)
```json
{
  "success": true,
  "data": {
    "nome_completo": "string | null",
    "data_nascimento": "string | null",
    "cpf": "string | null",
    "empresa": "string | null",
    "cnpj": "string | null",
    "nome_comprovante": "string | null",
    "cep": "string | null",
    "complemento": "string | null"
  }
}
```

## Exemplo de Execu
o
### Entrada:
```
**Nome Completo:** Maria Oliveira
**Data de Nascimento:** 20/04/1990
**CPF:** 987.654.321-00 - [REVISAR]
**Raz
o Social:** [ILEG
VEL]
**CNPJ:** 98.765.432/0001-10
```
### Sa
da JSON:
```json
{
  "success": true,
  "data": {
    "nome_completo": "Maria Oliveira",
    "data_nascimento": "20/04/1990",
    "cpf": "987.654.321-00 - [REVISAR]",
    "empresa": "[ILEG
VEL]",
    "cnpj": "98.765.432/0001-10",
    "nome_comprovante": null,
    "cep": null,
    "complemento": null
  }
}
```
"""

# --- Pydantic Models ---
class OCRData(BaseModel):
    nome_completo: Optional[str] = None
    data_nascimento: Optional[str] = None
    cpf: Optional[str] = None
    empresa: Optional[str] = None
    cnpj: Optional[str] = None
    nome_comprovante: Optional[str] = None
    cep: Optional[str] = None
    complemento: Optional[str] = None
    confidence_score: float = 0.0
    fields_extracted: int = 0
    fields_total: int = 8
    needs_review: List[str] = []

class OCRResponse(BaseModel):
    success: bool
    data: Optional[OCRData] = None
    error: Optional[str] = None
    raw_ocr_text: Optional[str] = None

# --- Global Doctr Model Loading (para o worker) ---
# O predictor ser
 carregado uma vez por processo de worker
predictor = None

def get_doctr_predictor():
    global predictor
    if predictor is None:
        print("Carregando modelos Doctr no worker... Isso pode levar alguns minutos.")
        predictor = ocr_predictor(pretrained=True)
        print("Modelos Doctr carregados com sucesso no worker.")
    return predictor

# --- Utility Functions ---
def format_date_to_yyyymmdd(date_str: str) -> Optional[str]:
    """
    Tenta formatar uma string de data para YYYY-MM-DD.
    Suporta DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD.
    """
    if not date_str:
        return None
    
    # Remove tags como [REVISAR] antes de tentar parsear
    cleaned_date_str = re.sub(r'\[.*?\]', '', date_str).strip()

    formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned_date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def calculate_metadata(data: OCRData, raw_llm_data: dict) -> OCRData:
    """
    Calcula fields_extracted, confidence_score e needs_review com base nos dados extra
dos.
    """
    fields_extracted = 0
    needs_review = []
    
    field_mapping = {
        "nome_completo": "nome_completo",
        "data_nascimento": "data_nascimento",
        "cpf": "cpf",
        "empresa": "empresa",
        "cnpj": "cnpj",
        "nome_comprovante": "nome_comprovante",
        "cep": "cep",
        "complemento": "complemento"
    }

    for llm_key, pydantic_key in field_mapping.items():
        value_from_llm = raw_llm_data.get("data", {}).get(llm_key)
        
        # Verifica se o campo foi extra
do (n
o 
 null e n
o 
 uma tag de erro)
        if getattr(data, pydantic_key) is not None and \
           str(getattr(data, pydantic_key)).strip().lower() not in ['[ileg
vel]', '[n
o encontrado]', '[n
o aplic
vel]']:
            fields_extracted += 1
        
        # Verifica se precisa de revis
o (baseado no texto original da LLM)
        if value_from_llm and (re.search(r'\[REVISAR\]', value_from_llm, re.IGNORECASE) or \
                               re.search(r'\[ILEG
VEL\]', value_from_llm, re.IGNORECASE)):
            needs_review.append(pydantic_key)

    data.fields_extracted = fields_extracted
    data.needs_review = list(set(needs_review)) # Remove duplicatas
    
    if data.fields_total > 0:
        data.confidence_score = round((fields_extracted - len(data.needs_review)) / data.fields_total, 2)
        if data.confidence_score < 0:
            data.confidence_score = 0.0
    else:
        data.confidence_score = 0.0

    return data

# --- LLM Integration Function ---
async def call_llm_for_json_extraction(raw_text: str) -> dict:
    """
    Chama a API da LLM para extrair e estruturar dados em JSON.
    """
    if not OPENAI_API_KEY:
        return {"success": False, "error": "OPENAI_API_KEY n
o configurada. N
o 
 poss
vel chamar a LLM.", "raw_ocr_text": raw_text}

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    formatted_prompt = LLM_PROMPT_TEMPLATE.format(raw_text_input=raw_text)

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": formatted_prompt
            }
        ],
        "response_format": { "type": "json_object" }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LLM_API_URL, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            llm_response_content = response.json()["choices"][0]["message"]["content"]
            
            try:
                parsed_json = json.loads(llm_response_content)
                return parsed_json
            except json.JSONDecodeError:
                if "Erro 0001" in llm_response_content:
                    return {"success": False, "error": llm_response_content}
                else:
                    return {"success": False, "error": f"Resposta da LLM n
o 
 um JSON v
lido: {llm_response_content}"}

        except httpx.RequestError as exc:
            return {"success": False, "error": f"Erro de rede ou requisi
o para a LLM: {exc}"}
        except httpx.HTTPStatusError as exc:
            return {"success": False, "error": f"Erro na API da LLM - Status {exc.response.status_code}: {exc.response.text}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado ao chamar a LLM: {str(e)}"}

# --- Main Task Function for RQ ---
async def process_single_document_task(image_bytes_b64: str) -> dict:
    """
    Processa uma 
nica imagem (base64) com Doctr e LLM.
    Esta fun
o ser
 enfileirada pelo RQ.
    """
    try:
        # 1. Decodificar a imagem base64
        image_bytes = io.BytesIO(base64.b64decode(image_bytes_b64))
        pil_image = Image.open(image_bytes)

        # 2. Processamento com Doctr
        predictor = get_doctr_predictor()
        doc = DocumentFile.from_images([pil_image])
        result = predictor(doc)

        raw_ocr_text = ""
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    raw_ocr_text += " ".join([word.value for word in line.words]) + "\n"
        
        # 3. Chamada para a LLM
        llm_processed_data = await call_llm_for_json_extraction(raw_ocr_text)

        if llm_processed_data.get("success", False):
            try:
                extracted_data = llm_processed_data.get("data", {})
                
                for key, value in extracted_data.items():
                    if isinstance(value, str):
                        cleaned_value = re.sub(r'\[.*?\]', '', value).strip()
                        extracted_data[key] = cleaned_value if cleaned_value else None

                if 'data_nascimento' in extracted_data and extracted_data['data_nascimento']:
                    extracted_data['data_nascimento'] = format_date_to_yyyymmdd(extracted_data['data_nascimento'])

                ocr_data = OCRData(**extracted_data)
                ocr_data = calculate_metadata(ocr_data, llm_processed_data)

                return {
                    "success": True,
                    "data": ocr_data.model_dump(),
                    "raw_ocr_text": raw_ocr_text
                }
            except ValidationError as e:
                return {
                    "success": False,
                    "error": f"Erro de valida
o do JSON da LLM com Pydantic: {e.errors()}",
                    "raw_ocr_text": raw_ocr_text
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Erro interno ao processar dados da LLM: {str(e)}",
                    "raw_ocr_text": raw_ocr_text
                }
        else:
            return {
                "success": False,
                "error": llm_processed_data.get("error", "Erro desconhecido da LLM"),
                "raw_ocr_text": raw_ocr_text
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Erro interno no worker durante o processamento: {str(e)}"
        }

