/**
 * Cliente API para comunicação com o backend FastAPI de OCR.
 */

interface ApiConfig {
  baseUrl: string;
  timeout: number;
}

class ApiClient {
  private config: ApiConfig;

  constructor(config?: Partial<ApiConfig>) {
    this.config = {
      baseUrl: process.env.NEXT_PUBLIC_OCR_API_URL || "http://localhost:8000",
      timeout: 60000, // 60 segundos
      ...config,
    };
  }

  private async fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  async processDocuments(documents: { [key: string]: File }): Promise<any> {
    const formData = new FormData();
    Object.entries(documents).forEach(([key, file]) => {
      formData.append("files", file, file.name);
    });

    const response = await this.fetchWithTimeout(`${this.config.baseUrl}/api/v1/ocr/process-documents`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  async getJobStatus(jobId: string): Promise<any> {
    const response = await this.fetchWithTimeout(`${this.config.baseUrl}/api/v1/ocr/job-status/${jobId}`, {
      method: "GET",
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  async healthCheck(): Promise<HealthStatus> {
    try {
      const response = await this.fetchWithTimeout(`${this.config.baseUrl}/health`, {
        method: "GET",
      });
      const data = await response.json();
      return {
        ok: response.ok,
        status: response.status,
        data,
      };
    } catch (error) {
      return {
        ok: false,
        status: 500,
        data: { error: error instanceof Error ? error.message : "Erro desconhecido" },
      };
    }
  }
}

// Instância singleton
export const apiClient = new ApiClient();

// Hook para usar em componentes React
export function useApiClient() {
  return apiClient;
}

// Tipos para TypeScript
export interface JobStatusResponse {
  job_id: string;
  status: "queued" | "started" | "finished" | "failed";
  result: any;
  error: string | null;
}

export interface HealthStatus {
  ok: boolean;
  status: number;
  data: any;
}

// Alias para compatibilidade com imports antigos
export { apiClient as api };
// (opcional) também como default
export default apiClient;

