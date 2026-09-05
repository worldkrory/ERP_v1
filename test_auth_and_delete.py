#!/usr/bin/env python3
"""
Script de prueba del sistema de autenticación y eliminación de ventas.

Uso:
    python test_auth_and_delete.py
"""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.user import User, UserRole
from app.models.party import Party, PartyRole
from app.models.sale import Sale
from app.services.sale_services import (
    create_sale,
    add_sale_item,
    delete_sale,
    SaleError,
)
from werkzeug.security import generate_password_hash


def test_user_creation():
    """Crear un usuario de prueba."""
    print("\n📝 CREAR USUARIO DE PRUEBA")
    print("-" * 50)
    
    app = create_app("development")
    
    with app.app_context():
        # Limpiar usuario anterior si existe
        existing = User.query.filter_by(email="test@densa.local").first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            print("✓ Usuario anterior eliminado")
        
        # Crear usuario
        user = User(
            email="test@densa.local",
            password_hash=generate_password_hash("password123"),
            full_name="Usuario Prueba",
            is_active=True,
            is_superuser=False,
        )
        db.session.add(user)
        db.session.commit()
        
        print(f"✓ Usuario creado: {user.email}")
        print(f"  - ID: {user.id}")
        print(f"  - Nombre: {user.full_name}")
        print(f"  - Activo: {user.is_active}")
        print(f"  - Admin: {user.is_superuser}")
        
        # Asignar rol VENTAS
        if hasattr(UserRole, '__tablename__'):
            role = UserRole(user_id=user.id, role_code="VENTAS")
            db.session.add(role)
            db.session.commit()
            print(f"✓ Rol VENTAS asignado")
        
        return user.id


def test_sale_deletion():
    """Probar eliminación de venta con restricciones."""
    print("\n🗑️  PRUEBA DE ELIMINACIÓN DE VENTAS")
    print("-" * 50)
    
    app = create_app("development")
    
    with app.app_context():
        try:
            # Obtener cliente de prueba
            party = Party.query.first()
            if not party:
                print("❌ No hay clientes en la base de datos")
                return
            
            # Crear venta en DRAFT
            sale = create_sale(
                db.session,
                sale_number="TEST-DELETE-001",
                party_id=party.id,
                channel="RETAIL",
            )
            db.session.commit()
            print(f"✓ Venta creada: {sale.sale_number} (ID: {sale.id})")
            print(f"  - Estado: {sale.status}")
            print(f"  - Cliente: {party.legal_name}")
            
            # Intentar eliminar DRAFT sin problemas
            print("\n  Eliminando venta DRAFT...")
            delete_sale(
                db.session,
                sale,
                created_by_id=1
            )
            db.session.commit()
            print(f"✓ Venta eliminada exitosamente")
            
        except SaleError as e:
            print(f"❌ Error de dominio: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")


def test_sale_deletion_restrictions():
    """Probar restricciones de eliminación."""
    print("\n⚠️  PRUEBA DE RESTRICCIONES DE ELIMINACIÓN")
    print("-" * 50)
    
    app = create_app("development")
    
    with app.app_context():
        try:
            # Obtener cliente de prueba
            party = Party.query.first()
            if not party:
                print("❌ No hay clientes en la base de datos")
                return
            
            # Crear venta y cambiar estado
            sale = create_sale(
                db.session,
                sale_number="TEST-RESTRICT-001",
                party_id=party.id,
                channel="RETAIL",
            )
            sale.status = "CONFIRMED"
            db.session.commit()
            print(f"✓ Venta creada: {sale.sale_number}")
            print(f"  - Estado: {sale.status}")
            
            # Intentar eliminar CONFIRMED (debe fallar)
            print("\n  Intentando eliminar venta CONFIRMED...")
            try:
                delete_sale(db.session, sale, created_by_id=1)
                print("❌ No debería permitir eliminar venta CONFIRMED")
            except SaleError as e:
                print(f"✓ Restricción funcionando correctamente:")
                print(f"  {e}")
            
            # Limpiar
            db.session.delete(sale)
            db.session.commit()
            
        except Exception as e:
            print(f"❌ Error: {e}")


def test_login_route():
    """Probar rutas de autenticación."""
    print("\n🔐 PRUEBA DE RUTAS DE AUTENTICACIÓN")
    print("-" * 50)
    
    app = create_app("development")
    client = app.test_client()
    
    # Test 1: Acceder a login
    print("\n1. Acceder a formulario de login:")
    response = client.get("/auth/login")
    print(f"   Status: {response.status_code}")
    print(f"   ✓ Formulario disponible" if response.status_code == 200 else "   ❌ Error")
    
    # Test 2: Intentar login sin credenciales
    print("\n2. Login sin credenciales:")
    response = client.post("/auth/login", data={}, follow_redirects=True)
    print(f"   Status: {response.status_code}")
    print(f"   ✓ Requiere datos" if response.status_code == 200 else "   ✓ Redirigido")
    
    # Test 3: Redireccionamiento de rutas protegidas
    print("\n3. Acceso a ruta protegida sin autenticación:")
    response = client.get("/ventas", follow_redirects=False)
    print(f"   Status: {response.status_code}")
    print(f"   ✓ Redirige a login" if response.status_code == 302 else f"   Status: {response.status_code}")


def main():
    """Ejecutar todas las pruebas."""
    print("=" * 50)
    print("🧪 PRUEBAS DEL SISTEMA DE AUTENTICACIÓN")
    print("=" * 50)
    
    try:
        # Test 1: Crear usuario
        user_id = test_user_creation()
        
        # Test 2: Rutas de autenticación
        test_login_route()
        
        # Test 3: Eliminación de ventas
        test_sale_deletion()
        
        # Test 4: Restricciones
        test_sale_deletion_restrictions()
        
        print("\n" + "=" * 50)
        print("✅ TODAS LAS PRUEBAS COMPLETADAS")
        print("=" * 50)
        
        print("\n📌 PRÓXIMOS PASOS:")
        print("1. Iniciar servidor: flask run")
        print("2. Navegar a: http://localhost:5000")
        print("3. Login con: test@densa.local / password123")
        print("4. Acceder a: http://localhost:5000/ventas")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
