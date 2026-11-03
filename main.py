"""Avvio: senza argomenti apre la GUI, con argomenti usa la CLI (python main.py file.pdf -p 1)."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from cameo_dxf.cli import main
        sys.exit(main())
    from cameo_dxf.gui import main
    main()
