export type AlertLevel = "CALM" | "SUSPICIOUS" | "ALERT" | "COMPROMISED";

export type Role =
  | "flank"
  | "breach"
  | "stealth-cover"
  | "overwatch"
  | "distract";

export interface VisibleEntity {
  entity_id: string;
  entity_type: string;
  position: [number, number];
  threat_level: number;
}

export interface PerceptionFrame {
  agent_id: string;
  tick: number;
  position: [number, number];
  heading: number;
  visibility_polygon: [number, number][];
  visible_entities?: VisibleEntity[];
  alert_level?: AlertLevel;
  ammo?: number;
  cooldown_ticks?: number;
}

export interface DoctrineUpdate {
  squad_id: string;
  role_weights: Partial<Record<Role, number>>;
  priority_objective?: string;
}

export interface RoleAward {
  agent_id: string;
  task_id: string;
  role: Role;
  utility: number;
}

export interface SquadDirective {
  squad_id: string;
  directive_seq: number;
  tick: number;
  awards: RoleAward[];
  objective_ref: string;
}

export interface DirectiveMessage {
  type: "directive";
  directive: SquadDirective;
  latency_ms: number;
  interrupted: boolean;
  replan_count: number;
  objective_ref: string;
  recovery_ms?: number;
}

export interface SquadState {
  squad_id: string;
  agent_ids: string[];
  tick: number;
  doctrine: DoctrineUpdate | null;
  last_directive: SquadDirective | null;
  objective_ref: string;
  scenario: Record<string, unknown> | null;
}

export interface CreateSquadRequest {
  agent_ids: string[];
  objective_ref?: string;
  scenario?: Record<string, unknown>;
}

export interface EventsResponse {
  squad_id: string;
  events: Array<{ id?: string; type: string; payload: unknown }>;
  total: number;
  truncated: boolean;
}
