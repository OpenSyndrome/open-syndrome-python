import marimo

__generated_with = "0.14.5"
app = marimo.App(
    width="medium",
    app_title="Open Syndrome Definition - Data Browser",
)


@app.cell
def _():
    import marimo as mo
    import json
    from pathlib import Path
    import os

    from flatten_json import flatten
    import polars as pl
    import plotly.graph_objects as go
    from dotenv import load_dotenv

    from osi.filtering import (
        filter_cases_per_definitions,
        load_definition,
        overlap_definitions,
    )

    return (
        Path,
        filter_cases_per_definitions,
        flatten,
        go,
        json,
        load_definition,
        load_dotenv,
        mo,
        os,
        overlap_definitions,
        pl,
    )


@app.cell(hide_code=True)
def _(load_dotenv):
    result = load_dotenv()  # noqa
    return


@app.cell
def _(go, pl):
    def plot_cases(_df_filtered, definitions, date_column="date"):
        _definitions_columns_sum = [
            pl.col(definition).sum().alias(definition) for definition in definitions
        ]
        _agg_df = (
            _df_filtered.group_by(date_column)
            .agg(_definitions_columns_sum)
            .sort(date_column)
        )
        _fig = go.Figure()
        for definition in definitions:
            _fig.add_trace(
                go.Scatter(
                    x=_agg_df[date_column],
                    y=_agg_df[definition],
                    mode="lines+markers",
                    name=definition,
                )
            )
        return _fig

    return (plot_cases,)


@app.cell
def _(go, pl):
    def groupped_bar(_df_filtered, definitions, group_by_column="code", top_n=10):
        _agg_df = (
            _df_filtered.group_by(group_by_column)
            .agg([pl.col(definition).sum() for definition in definitions])
            .sort(group_by_column)
        )

        _agg_df = _agg_df.with_columns(
            (sum([pl.col(definition) for definition in definitions])).alias("total")
        )
        _agg_df = _agg_df.sort("total", descending=True).head(
            top_n
        )  # .sort(group_by_column)
        _fig = go.Figure(
            data=[
                go.Bar(
                    name=definition, x=_agg_df[group_by_column], y=_agg_df[definition]
                )
                for definition in definitions
            ]
        )
        _fig.update_layout(barmode="group")
        return _fig

    return (groupped_bar,)


@app.cell
def _(mo):
    mo.md(r"""# Open Syndrome Definition 👩🏽‍🔬""")
    return


@app.cell
def _(mo):
    mo.callout(
        "This is a prototype of how to filter your data using definitions from the Open Syndrome Initiative.",
        kind="neutral",
    )
    return


@app.cell
def _(json, mo):
    empty_mapping = [
        {"system": "CID 10", "code": "icd_code"},
        {"system": "ICD-10", "code": "icd_code"},
        {"system": "CID", "code": "icd_code"},
    ]
    mapping_editor = mo.ui.code_editor(
        value=json.dumps(empty_mapping, indent=2), language="javascript"
    )  # json

    mapping_form = (
        mo.md(
            """
        {date_column}

        {code_column}

        {mapping}
    """
        )
        .batch(
            date_column=mo.ui.text(label="Datetime column", placeholder="recording_ts"),
            code_column=mo.ui.text(
                label="Diagnosis code column", placeholder="icd_code"
            ),
            mapping=mapping_editor,
        )
        .form(bordered=True)
    )
    return (mapping_form,)


@app.cell
def _(mo):
    sample_file = mo.ui.file(
        kind="area", filetypes=[".csv"]
    )  # TODO max_size: int = 100000000 - the maximum file size is 100MB
    sample_file  # return is (name, contents)
    return (sample_file,)


@app.cell
def _(pl):
    def load_df_selected(sample_file):
        if not sample_file.value:
            return
        return pl.read_csv(sample_file.contents())

    return (load_df_selected,)


@app.cell
def _(load_df_selected, sample_file):
    df_selected = load_df_selected(sample_file)
    return (df_selected,)


@app.cell
def _(df_selected, mapping_form, mo):
    mo.stop(df_selected is None)

    mo.vstack(
        [
            mo.md("### **Data**"),
            mo.ui.dataframe(df_selected),
            mo.accordion(
                {
                    "Mapping configuration": mapping_form,
                }
            ),
        ]
    )
    return


@app.cell
def _(json, mapping_form, mo):
    mo.stop(mapping_form.value is None)

    date_column = mapping_form.value["date_column"]
    code_column = mapping_form.value["code_column"]
    mapping = json.loads(mapping_form.value["mapping"])
    return code_column, date_column, mapping


@app.cell
def _(Path, os):
    definition_options = {
        filepath.name.replace(".json", ""): filepath
        for filepath in Path(os.getenv("PROTOTYPE_DEFINITIONS_DIR")).glob(
            "**/*.json"
        )  # TODO fetch from a remote URL
    }
    return (definition_options,)


@app.cell
def _(definition_options, mo):
    definitions_dropdown = mo.ui.multiselect(
        label="Select Syndromic Indicators", options=sorted(definition_options.keys())
    )
    return (definitions_dropdown,)


@app.cell
def _(flatten, go, load_definition, mo, pl):
    def plot_flatted_json(df):
        cols = df.columns
        _fig = go.Figure(
            data=[
                go.Table(
                    header=dict(values=cols),
                    cells=dict(
                        values=[df[col] for col in cols],
                        fill_color="lavender",
                        align="left",
                    ),
                )
            ]
        )
        _fig.show()
        return _fig

    def flat_df(json_data, name):
        flat = flatten(json_data, separator=".")
        return pl.DataFrame(
            {
                "definition": name or json_data.get("title"),
                "field": flat.keys(),
                "value": flat.values(),
            },
            strict=False,
        )

    def flat_definitions(definitions):
        flatted = [
            flat_df(
                {
                    "inclusion_criteria": load_definition(definition_name)[
                        "inclusion_criteria"
                    ]
                },
                definition_name,
            )
            for definition_name in definitions
        ]
        table = pl.concat(flatted, how="vertical_relaxed").pivot(
            index=["definition"], on="field"
        )
        table = table.transpose(include_header=True, header_name="fields")
        table.rename(dict(zip(table.columns[1:], table.row(0)[1:]))).slice(1)
        return plot_flatted_json(table)  # FIXME

    def plot_comparison_between_definitions(definitions, overlapped):
        # return mo.ui.plotly(flat_definitions(definitions))
        return mo.md(",".join(overlapped) if overlapped else "-")

    return (plot_comparison_between_definitions,)


@app.cell
def _(definitions_dropdown, mo):
    mo.hstack([mo.md("**::lucide:filter:: Filters:**"), definitions_dropdown])
    return


@app.cell
def _(
    definitions_dropdown,
    df_selected,
    filter_cases_per_definitions,
    mapping,
    mo,
    overlap_definitions,
):
    mo.stop(
        df_selected is None
        or df_selected.is_empty()
        or definitions_dropdown.value is None
        or mapping is None
    )

    definitions = None
    df_filtered = None
    overlapped = None

    if not df_selected.is_empty():
        definitions = definitions_dropdown.value
        df_filtered = filter_cases_per_definitions(df_selected, mapping, definitions)
        overlapped = overlap_definitions(definitions)
    return definitions, df_filtered, overlapped


@app.cell
def _(definitions, df_filtered, df_selected, mo, overlapped):
    mo.stop(definitions is None or df_filtered is None)

    _cards = [
        mo.stat(
            label="Rows & columns",
            value=df_selected.shape[0],
        ),
        mo.stat(
            label="Columns",
            value=df_selected.shape[1],
        ),
        mo.stat(
            label="Syndromic Indicators",
            value=len(definitions),
            caption=", ".join([definition for definition in definitions]),
            bordered=True,
        ),
        mo.stat(
            label="Number of common criteria",
            value=len(overlapped) if overlapped else "-",
        ),
    ]

    _title = "## Data with Open Syndrome Definitions"

    mo.vstack(
        [
            mo.md(_title),
            mo.hstack(_cards, widths="equal", align="center"),
        ]
    )
    return


@app.cell
def _(
    definitions,
    load_definition,
    mo,
    overlapped,
    plot_comparison_between_definitions,
):
    mo.stop(definitions is None)

    mo.vstack(
        [
            mo.md("### Definitions details"),
            mo.md(
                "This section shows the definitions used to filter the data. You can use them to understand how the data was filtered and what criteria were applied. 🔎"
            ),
            mo.ui.tabs(
                {
                    "In common": plot_comparison_between_definitions(
                        definitions, overlapped
                    ),
                    "JSONs": mo.accordion(
                        {
                            definition: mo.json(load_definition(definition))
                            for definition in definitions
                        }
                    ),
                },
            ),
        ]
    )
    return


@app.cell
def _(mo):
    top_n = mo.ui.number(start=1, stop=10, label="Number of top codes", value=3, step=1)
    return (top_n,)


@app.cell
def _(
    code_column,
    date_column,
    definitions,
    df_filtered,
    df_selected,
    groupped_bar,
    mo,
    plot_cases,
    top_n,
):
    mo.stop(definitions is None or df_selected is None)

    mo.vstack(
        [
            mo.md("## Time series"),
            plot_cases(df_filtered, definitions, date_column=date_column),
            mo.md("## Codes comparison per syndromic indicator"),
            top_n.left(),
            groupped_bar(
                df_filtered,
                definitions,
                top_n=top_n.value or 3,
                group_by_column=code_column,
            ),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
