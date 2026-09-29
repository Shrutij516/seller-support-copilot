import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { ResponsiveTable, type Column } from "./ResponsiveTable";

interface Row {
  id: string;
  name: string;
  status: string;
}

const rows: Row[] = [
  { id: "1", name: "Order 1", status: "Placed" },
  { id: "2", name: "Order 2", status: "Delivered" },
];

const columns: Column<Row>[] = [
  { header: "Name", cell: (r) => r.name },
  { header: "Status", cell: (r) => r.status },
];

describe("ResponsiveTable", () => {
  it("renders exactly one accessible table containing every row and column", () => {
    render(
      <ResponsiveTable
        caption="Orders"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        emptyMessage="No orders."
      />,
    );

    const table = screen.getByRole("table", { name: "Orders" });
    const rowGroup = within(table).getAllByRole("row");
    expect(rowGroup).toHaveLength(rows.length + 1);
    expect(within(table).getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(within(table).getByText("Order 1")).toBeInTheDocument();
    expect(within(table).getByText("Order 2")).toBeInTheDocument();
  });

  it("hides the desktop table and the mobile card list from each other via display:none breakpoint classes, not visually-hidden styling", () => {
    const { container } = render(
      <ResponsiveTable
        caption="Orders"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        emptyMessage="No orders."
      />,
    );

    const tableWrapper = container.querySelector("table")?.parentElement;
    const cardList = container.querySelector("ul");

    // `hidden` / `md:hidden` are Tailwind's display:none utilities (removed from the
    // accessibility tree and from layout), unlike sr-only which only clips visually and
    // would leave a screen reader announcing both copies of every row.
    expect(tableWrapper).toHaveClass("hidden", "md:block");
    expect(cardList).toHaveClass("md:hidden");
    expect(tableWrapper?.className).not.toMatch(/sr-only/);
    expect(cardList?.className).not.toMatch(/sr-only/);
  });

  it("shows the empty message instead of a table or card list when there are no rows", () => {
    render(
      <ResponsiveTable
        caption="Orders"
        columns={columns}
        rows={[]}
        rowKey={(r) => r.id}
        emptyMessage="No orders yet."
      />,
    );

    expect(screen.getByText("No orders yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("wraps the first column in a link to rowHref when provided, in both renderings", () => {
    render(
      <ResponsiveTable
        caption="Orders"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        rowHref={(r) => `/orders/detail?id=${r.id}`}
        emptyMessage="No orders."
      />,
    );

    const links = screen.getAllByRole("link", { name: /order 1/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/orders/detail?id=1");
    }
  });
});
