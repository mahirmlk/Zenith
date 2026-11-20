import { describe, expect, it } from "vitest";
import { buildBackendEnvironment, forwardToBackend, requestForBackend } from "./proxy";

describe("backend gateway request forwarding", () => {
  it("sets production invariants and only forwards configured values", () => {
    const env = buildBackendEnvironment({
      APP_URL: "https://zenith.example",
      SUPABASE_URL: "https://project.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "test-only-secret",
      REDIS_URL: "rediss://cache.example.test",
      DATABASE_URL: "postgresql://app:secret@db.example.test/zenith?sslmode=require",
      OPENROUTER_API_KEY: undefined,
    });

    expect(env).toEqual({
      APP_ENV: "production",
      LANGGRAPH_STRICT_MSGPACK: "true",
      APP_URL: "https://zenith.example",
      SUPABASE_URL: "https://project.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "test-only-secret",
      REDIS_URL: "rediss://cache.example.test",
      DATABASE_URL: "postgresql://app:secret@db.example.test/zenith?sslmode=require",
    });
    expect(env).not.toHaveProperty("OPENROUTER_API_KEY");
  });

  it("preserves path, query, method, headers, and streaming request bodies", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("payload"));
        controller.close();
      },
    });
    const original = new Request("https://api.zenith.example/api/events?cursor=17", {
      method: "POST",
      headers: { authorization: "Bearer test-token", "content-type": "text/plain" },
      body,
      // Workers accept streaming Request bodies without buffering.
      duplex: "half",
    } as RequestInit & { duplex: "half" });

    const forwarded = requestForBackend(original);

    expect(forwarded.url).toBe("http://container/api/events?cursor=17");
    expect(forwarded.method).toBe("POST");
    expect(forwarded.headers.get("authorization")).toBe("Bearer test-token");
    expect(forwarded.headers.get("content-type")).toBe("text/plain");
    expect(await forwarded.text()).toBe("payload");
  });

  it("returns the original SSE response so the caller can stream it", async () => {
    const upstream = new Response(
      new ReadableStream<Uint8Array>({
        pull(controller) {
          controller.enqueue(new TextEncoder().encode("data: connected\n\n"));
          controller.close();
        },
      }),
      { headers: { "content-type": "text/event-stream" } },
    );
    const port = {
      fetch: async () => upstream,
    } as unknown as Fetcher;

    const response = await forwardToBackend(
      port,
      new Request("https://api.zenith.example/api/runs/run-1/events"),
    );

    expect(response).toBe(upstream);
    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(await response.text()).toBe("data: connected\n\n");
  });
});
