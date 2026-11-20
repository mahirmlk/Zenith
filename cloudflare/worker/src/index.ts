import { DurableObject } from "cloudflare:workers";
import { buildBackendEnvironment, forwardToBackend } from "./proxy";

const BACKEND_PORT = 8000;
const SINGLETON_NAME = "zenith-production-backend";
const HEARTBEAT_PATH = "/_zenith_internal/heartbeat";
const INACTIVITY_TIMEOUT_MS = 150_000;
const READY_ATTEMPTS = 80;
const READY_INTERVAL_MS = 500;
const READY_REQUEST_TIMEOUT_MS = 3_000;

export class ZenithBackendContainer extends DurableObject<Cloudflare.Env> {
  private starting: Promise<void> | undefined;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === HEARTBEAT_PATH && request.method === "POST") {
      await this.ensureBackendReady();
      const response = await this.backendPort().fetch(
        "http://container:8000/api/health",
        { signal: AbortSignal.timeout(READY_REQUEST_TIMEOUT_MS) },
      );
      await response.body?.cancel();
      if (!response.ok) {
        return new Response("Backend health probe failed", { status: 503 });
      }
      return new Response(null, { status: 204 });
    }

    await this.ensureBackendReady();
    // Return Fetcher's streaming response directly so SSE is never buffered.
    return forwardToBackend(this.backendPort(), request);
  }

  private backendPort(): Fetcher {
    const container = this.ctx.container;
    if (!container) {
      throw new Error("Backend Container binding is unavailable");
    }
    return container.getTcpPort(BACKEND_PORT);
  }

  private async ensureBackendReady(): Promise<void> {
    this.starting ??= this.startAndProbe().finally(() => {
      this.starting = undefined;
    });
    await this.starting;
    await this.ctx.container?.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);
  }

  private async startAndProbe(): Promise<void> {
    const container = this.ctx.container;
    if (!container) {
      throw new Error("Backend Container binding is unavailable");
    }

    const missingRequired = [
      "APP_URL",
      "SUPABASE_URL",
      "SUPABASE_SERVICE_ROLE_KEY",
      "REDIS_URL",
      "DATABASE_URL",
    ].filter((key) => !this.env[key as keyof Cloudflare.Env]);
    if (missingRequired.length > 0) {
      throw new Error(`Missing required Worker secrets: ${missingRequired.join(", ")}`);
    }

    if (!container.running) {
      container.start({
        image: container.images.backend,
        instance: "standard-1",
        enableInternet: true,
        env: buildBackendEnvironment(this.env),
      });
    }

    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);
    let lastFailure: unknown;

    for (let attempt = 0; attempt < READY_ATTEMPTS; attempt += 1) {
      try {
        const response = await container
          .getTcpPort(BACKEND_PORT)
          .fetch("http://container:8000/api/ready", {
            signal: AbortSignal.timeout(READY_REQUEST_TIMEOUT_MS),
          });
        await response.body?.cancel();
        if (response.ok) {
          return;
        }
        lastFailure = new Error(`Readiness endpoint returned ${response.status}`);
      } catch (error) {
        lastFailure = error;
      }

      if (attempt + 1 < READY_ATTEMPTS) {
        await new Promise<void>((resolve) => setTimeout(resolve, READY_INTERVAL_MS));
      }
    }

    console.error("Zenith backend failed its readiness probe", {
      attempts: READY_ATTEMPTS,
      reason: lastFailure instanceof Error ? lastFailure.name : "unknown",
    });
    throw new Error("Zenith backend did not become ready within the startup window");
  }
}

const notFound = () => new Response("Not found", { status: 404 });

export default {
  async fetch(request: Request, env: Cloudflare.Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    // The heartbeat is only callable through the scheduled handler below.
    if (pathname === HEARTBEAT_PATH) {
      return notFound();
    }

    try {
      return await env.ZENITH_BACKEND.getByName(SINGLETON_NAME).fetch(request);
    } catch {
      return Response.json(
        { detail: "Backend is starting or temporarily unavailable" },
        { status: 503, headers: { "Retry-After": "5" } },
      );
    }
  },

  async scheduled(
    _controller: ScheduledController,
    env: Cloudflare.Env,
  ): Promise<void> {
    const heartbeat = new Request(`https://gateway.internal${HEARTBEAT_PATH}`, {
      method: "POST",
    });
    const response = await env.ZENITH_BACKEND.getByName(SINGLETON_NAME).fetch(heartbeat);
    await response.body?.cancel();
    if (!response.ok) {
      throw new Error(`Zenith backend heartbeat failed with status ${response.status}`);
    }
  },
} satisfies ExportedHandler<Cloudflare.Env>;
