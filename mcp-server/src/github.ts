const GITHUB_API = "https://api.github.com";

function getToken(): string {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error(
      "GITHUB_TOKEN environment variable is not set. " +
        "Set it to a GitHub Personal Access Token or App installation token."
    );
  }
  return token;
}

function baseHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    Authorization: `Bearer ${getToken()}`,
    Accept: extra.accept ?? "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "devmind-github-mcp/1.0",
    ...extra,
  };
}

export async function githubRequest(
  path: string,
  extraHeaders: Record<string, string> = {}
): Promise<unknown> {
  const url = path.startsWith("http") ? path : `${GITHUB_API}${path}`;
  const headers = baseHeaders(extraHeaders);

  const res = await fetch(url, { headers });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub API error ${res.status} for ${path}: ${text}`);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

export async function githubPost(path: string, body: unknown): Promise<Record<string, unknown>> {
  const url = `${GITHUB_API}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      ...baseHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub API error ${res.status} for POST ${path}: ${text}`);
  }

  return res.json() as Promise<Record<string, unknown>>;
}
