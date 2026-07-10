from __future__ import annotations

from workflows.rfgun_hom_eigenmode.diagnostics import (
    archived_hdf5_mode_pairs,
    classify_solver_failure,
    parse_attempt_diagnostics,
)


def test_mode_field_names_are_configuration_driven() -> None:
    archived = [
        {"relative_path": "electric_mode_2.h5"},
        {"relative_path": "magnetic_mode_2.h5"},
    ]

    assert archived_hdf5_mode_pairs(
        archived,
        {
            "e": "electric_mode_{mode}.h5",
            "h": "magnetic_mode_{mode}.h5",
        },
    ) == {2: {"e", "h"}}


def test_message_parser_uses_final_mode_table_and_sticky_port_warnings() -> None:
    messages = [
        {
            "type": "INFO",
            "text": (
                "Eigenmode solver results:\n"
                "  Mode Frequency Total Q Accuracy\n"
                "  1 1000.0 MHz 10 1e-6\n"
                "  2 1001.0 MHz 20 1e-6\n"
                "  3 1002.0 MHz 30 1e-6\n"
            ),
        },
        {
            "type": "WARNING",
            "text": "At least one propagating mode is not considered at port 4.",
        },
        {
            "type": "INFO",
            "text": (
                "Eigenmode solver results:\n"
                "  Mode Frequency Total Q Accuracy\n"
                "  1 1000.1 MHz 10 1e-8\n"
                "  2 1001.1 MHz 20 1e-8\n"
            ),
        },
        {"type": "INFO", "text": "Meshing successful"},
        {"type": "INFO", "text": "Eigenmode solver successful"},
    ]

    diagnostics = parse_attempt_diagnostics(messages)

    assert diagnostics.final_mode_numbers == (1, 2)
    assert diagnostics.mode_table_present is True
    assert diagnostics.final_mode_frequencies_hz == (
        (1, 1000.1e6),
        (2, 1001.1e6),
    )
    assert diagnostics.propagating_warning_ports == (4,)
    assert diagnostics.boundary_sensitive is True
    assert diagnostics.warning_codes == (
        "propagating_port_modes_not_considered:4",
    )


def test_fast_failure_requires_no_mesh_no_mode_table_and_short_elapsed() -> None:
    empty = parse_attempt_diagnostics(
        [{"type": "ERROR", "text": "Could not read mesh."}]
    )
    meshed = parse_attempt_diagnostics(
        [
            {"type": "INFO", "text": "Meshing successful"},
            {"type": "ERROR", "text": "Tetrahedral Meshing: Terminated"},
        ]
    )

    assert (
        classify_solver_failure(
            empty, elapsed_s=6, long_attempt_threshold_s=120
        )
        == "init_fast"
    )
    assert (
        classify_solver_failure(
            empty, elapsed_s=600, long_attempt_threshold_s=120
        )
        == "init_fast"
    )
    assert (
        classify_solver_failure(
            meshed, elapsed_s=6, long_attempt_threshold_s=120
        )
        == "long_solve"
    )


def test_empty_final_mode_table_is_a_valid_long_solver_result() -> None:
    diagnostics = parse_attempt_diagnostics(
        [
            {
                "type": "INFO",
                "text": (
                    "Mode Frequency [MHz] Total Q Accuracy\n"
                    "1 999.000 MHz 10 1e-6"
                ),
            },
            {
                "type": "INFO",
                "text": "Mode Frequency [MHz] Total Q Accuracy\n",
            },
            {"type": "INFO", "text": "Eigenmode solver successful"},
        ]
    )

    assert diagnostics.mode_table_present is True
    assert diagnostics.final_mode_numbers == ()
    assert (
        classify_solver_failure(
            diagnostics,
            elapsed_s=5,
            long_attempt_threshold_s=120,
        )
        == "long_solve"
    )
