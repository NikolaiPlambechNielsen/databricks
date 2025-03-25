CREATE TABLE IF NOT EXISTS dap_x_silver.caboodle.patientdim (
    encounterkey bigint not null,
    patientdurablekey bigint,
    departmentkey bigint,
    visitkey bigint
)