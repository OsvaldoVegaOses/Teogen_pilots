import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Opciones para despliegue en Azure
  output: "export", // Esto genera una aplicación estática
  trailingSlash: true, // Asegura que todas las rutas tengan slash final
  images: {
    unoptimized: true // Deshabilita la optimización de imágenes para despliegue estático
  },
  // Otras configuraciones
  reactStrictMode: true,
};

export default nextConfig;