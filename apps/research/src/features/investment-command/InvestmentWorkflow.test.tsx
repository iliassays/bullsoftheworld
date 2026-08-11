import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { InvestmentWorkflow } from "./InvestmentWorkflow";

describe("InvestmentWorkflow", () => {
  it("explains the gated decision path and links every stage", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <InvestmentWorkflow
          bookCount={2}
          catalystCount={3}
          researchAttention={4}
          reviewCount={1}
          targetCount={2}
        />
      </MemoryRouter>,
    );

    expect(html).toContain("How Atlas reaches a paper decision");
    expect(html).toContain("Discover → Investigate → Validate → Allocate → Learn");
    expect(html).toContain("cannot become a paper target until a registered strategy passes");
    expect(html).toContain('href="/setups"');
    expect(html).toContain('href="/queue"');
    expect(html).toContain('href="/hypotheses"');
    expect(html).toContain('href="/portfolio"');
    expect(html).toContain('href="/memory"');
    expect(html).toContain("4 evidence briefs require attention");
    expect(html).toContain("2 target changes · 1 risk review");
    expect(html).toContain("2 paper books · immutable forward outcomes");
  });

  it("uses singular labels and an explicit zero-attention state", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <InvestmentWorkflow
          bookCount={1}
          catalystCount={1}
          researchAttention={0}
          reviewCount={0}
          targetCount={1}
        />
      </MemoryRouter>,
    );

    expect(html).toContain("1 dated catalyst plus point-in-time setup scans");
    expect(html).toContain("No fresh evidence brief requires attention");
    expect(html).toContain("1 target change · 0 risk reviews");
    expect(html).toContain("1 paper book · immutable forward outcomes");
  });
});
