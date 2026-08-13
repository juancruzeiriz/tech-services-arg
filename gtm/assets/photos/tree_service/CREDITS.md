# Fotos — tree_service

Fuente: **Unsplash**. La [licencia de Unsplash](https://unsplash.com/license) permite uso
comercial, incluido trabajo para clientes, **sin atribución**. Este archivo no existe porque
la licencia lo exija, sino para poder auditar de dónde salió cada archivo del repo.

> Se intentó primero Pexels (la fuente que se había acordado). Su sitio devuelve **403 a
> acceso automatizado**; no se intentó evadir esa protección, se cambió de fuente. La
> licencia de Unsplash es equivalente para este uso: comercial, sin atribución.

## Criterio de selección

**Sin caras identificables.** La licencia de Unsplash no incluye *model release*, así que un
rostro reconocible en el sitio de otro negocio es riesgo de derechos de imagen — no de
copyright. Las 7 fotos se revisaron una por una antes de bajarlas: en todas la cara está
tapada por casco/visor, de espaldas, a contraluz o directamente fuera de cuadro. Se descartó
una candidata buena (`photo-1684332666088`, manos con motosierra) porque tenía un perfil
parcial en el borde.

Si se agregan fotos nuevas, aplicar el mismo filtro.

## Archivos

| Archivo | Origen | Contenido |
|---|---|---|
| `hero-1.webp` | [photo-1697623317093](https://unsplash.com/photos/1697623317093-7a50b4aaf676) | Troncos cortados en un parque, sin gente |
| `hero-2.webp` | [photo-1674240993086](https://unsplash.com/photos/1674240993086-fd2fed32c556) | Operario en plataforma elevadora, casco naranja |
| `hero-3.webp` | [photo-1626828476637](https://unsplash.com/photos/1626828476637-5bd713ef9f22) | Trepador con motosierra en un pino |
| `work-1.webp` | [photo-1657730391002](https://unsplash.com/photos/1657730391002-bf55ff069a80) | Trabajo con cuerdas sobre una rama |
| `work-2.webp` | [photo-1574359173269](https://unsplash.com/photos/1574359173269-291f060e6fe1) | Tronco caído en primer plano, corte al fondo |
| `work-3.webp` | [photo-1588878309774](https://unsplash.com/photos/1588878309774-4b3f42a19a8f) | Trepador contra cielo azul, cortando una rama |
| `work-4.webp` | [photo-1515446134809](https://unsplash.com/photos/1515446134809-993c501ca304) | Anillos de un tronco, textura |

Bajadas del CDN de Unsplash ya redimensionadas y en WebP (`?w=&h=&fit=crop&q=&fm=webp`), así
que **no hace falta ninguna dependencia de procesamiento de imágenes** en `requirements.txt`.
Heroes recortados a 1200×760; galería a 700px de ancho.
