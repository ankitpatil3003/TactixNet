import WebSocket from "ws";

import type {
  CreateSquadRequest,
  DirectiveMessage,
  DoctrineUpdate,
  EventsResponse,
  PerceptionFrame,
  SquadState,
} from "./types.js";

export interface SquadClientOptions {
  gateway: string;
  squadId?: string;
}

export class SquadClient {
  readonly gateway: string;
  squadId: string | null;

  private http: typeof fetch;
  private ws: WebSocket | null = null;

  constructor(options: SquadClientOptions) {
    this.gateway = options.gateway.replace(/\/$/, "");
    this.squadId = options.squadId ?? null;
    this.http = globalThis.fetch.bind(globalThis);
  }

  static async create(
    gateway: string,
    agentIds: string[],
    options?: {
      objectiveRef?: string;
      scenario?: Record<string, unknown>;
      fetchImpl?: typeof fetch;
    },
  ): Promise<SquadClient> {
    const client = new SquadClient({ gateway });
    if (options?.fetchImpl) {
      client.http = options.fetchImpl;
    }
    const body: CreateSquadRequest = { agent_ids: agentIds };
    if (options?.objectiveRef !== undefined) {
      body.objective_ref = options.objectiveRef;
    }
    if (options?.scenario !== undefined) {
      body.scenario = options.scenario;
    }
    const response = await client.http(`${client.gateway}/squads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`create squad failed: HTTP ${response.status}`);
    }
    const data = (await response.json()) as SquadState;
    client.squadId = data.squad_id;
    return client;
  }

  private requireSquadId(): string {
    if (!this.squadId) {
      throw new Error("squadId is required");
    }
    return this.squadId;
  }

  private wsUrl(observer = false): string {
    const squadId = this.requireSquadId();
    const base = this.gateway.replace(/^http/, "ws");
    const mode = observer ? "?mode=observer" : "";
    return `${base}/ws/squads/${squadId}${mode}`;
  }

  async connect(options?: { observer?: boolean }): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(this.wsUrl(options?.observer));
      socket.once("open", () => {
        this.ws = socket;
        resolve();
      });
      socket.once("error", reject);
    });
  }

  async sendFrame(frame: PerceptionFrame): Promise<void> {
    if (!this.ws) {
      throw new Error("WebSocket not connected");
    }
    this.ws.send(JSON.stringify(frame));
  }

  async sendSnapshot(snapshot: Record<string, unknown>): Promise<void> {
    if (!this.ws) {
      throw new Error("WebSocket not connected");
    }
    this.ws.send(JSON.stringify(snapshot));
  }

  async receiveJson(): Promise<Record<string, unknown>> {
    if (!this.ws) {
      throw new Error("WebSocket not connected");
    }
    const raw = await new Promise<string>((resolve, reject) => {
      this.ws!.once("message", (data) => resolve(data.toString()));
      this.ws!.once("error", reject);
    });
    return JSON.parse(raw) as Record<string, unknown>;
  }

  async receiveDirective(): Promise<DirectiveMessage> {
    while (true) {
      const message = await this.receiveJson();
      if (message.type === "directive") {
        return message as unknown as DirectiveMessage;
      }
      if (message.type === "error") {
        throw new Error(String(message.message ?? "gateway error"));
      }
    }
  }

  async applyDoctrine(doctrine: DoctrineUpdate): Promise<SquadState> {
    const squadId = this.requireSquadId();
    const response = await this.http(`${this.gateway}/squads/${squadId}/doctrine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doctrine),
    });
    if (!response.ok) {
      throw new Error(`apply doctrine failed: HTTP ${response.status}`);
    }
    return (await response.json()) as SquadState;
  }

  async getState(): Promise<SquadState> {
    const squadId = this.requireSquadId();
    const response = await this.http(`${this.gateway}/squads/${squadId}`);
    if (!response.ok) {
      throw new Error(`get state failed: HTTP ${response.status}`);
    }
    return (await response.json()) as SquadState;
  }

  async getScenario(): Promise<{ squad_id: string; scenario: Record<string, unknown> }> {
    const squadId = this.requireSquadId();
    const response = await this.http(`${this.gateway}/squads/${squadId}/scenario`);
    if (!response.ok) {
      throw new Error(`get scenario failed: HTTP ${response.status}`);
    }
    return (await response.json()) as { squad_id: string; scenario: Record<string, unknown> };
  }

  async getEvents(options?: {
    count?: number;
    replayOnly?: boolean;
  }): Promise<EventsResponse> {
    const squadId = this.requireSquadId();
    const params = new URLSearchParams();
    if (options?.count !== undefined) {
      params.set("count", String(options.count));
    }
    if (options?.replayOnly) {
      params.set("replay_only", "true");
    }
    const query = params.toString();
    const url = `${this.gateway}/squads/${squadId}/events${query ? `?${query}` : ""}`;
    const response = await this.http(url);
    if (!response.ok) {
      throw new Error(`get events failed: HTTP ${response.status}`);
    }
    return (await response.json()) as EventsResponse;
  }

  async close(): Promise<void> {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
