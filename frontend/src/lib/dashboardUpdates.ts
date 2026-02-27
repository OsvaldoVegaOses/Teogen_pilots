export type DashboardUpdateItem = {
    title: string;
    description: string;
};

export const DASHBOARD_UPDATES_VERSION = "2026-02-27";

export const DASHBOARD_UPDATES: DashboardUpdateItem[] = [
    {
        title: "Sesion personalizable",
        description: "Ahora puedes definir nombre visible y organizacion o cargo desde 'Editar perfil'.",
    },
    {
        title: "Avatar de usuario",
        description: "La cabecera muestra iniciales dinamicas para identificar rapidamente la sesion activa.",
    },
    {
        title: "Cierre de sesion limpio",
        description: "El boton 'Cerrar sesion' elimina tokens y cache local relevante del navegador.",
    },
    {
        title: "Asistente mejorado",
        description: "El asistente cuenta con soporte operativo, metricas y panel de operaciones recientes.",
    },
];
