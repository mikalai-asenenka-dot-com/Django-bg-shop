# pylint: skip-file
import os
import csv
import json
import io
from pathlib import Path
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from boardgamegeek import BGGClient

from django.contrib import messages
from django.shortcuts import render
from django.conf import settings
from django.views.generic import ListView, DetailView, FormView, View
from django.http import HttpResponseRedirect, HttpResponse,FileResponse
from django.urls import reverse_lazy
from django.contrib.sessions.models import Session
from django.http import JsonResponse

from .models import BoardGame, Cart, CartProduct, Order
from .forms import Submit_BG_form, Search_BG_form
from .mixins import SuggestionFormMixin, CartMixin


class BoardGamesListView(CartMixin, SuggestionFormMixin, ListView):

    model = BoardGame
    template_name = "home.html"
    context_object_name = "boardgames"

    def dispatch(self, request, *args, **kwargs):
        if "max_searched_bgs" in  request.session.keys():
            request.session.pop("max_searched_bgs")
        if "searched_val" in request.session.keys():            
            request.session.pop("searched_val")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_form"] = Search_BG_form()
        context["max_bgs"] = self.model.objects.count()
        return context

    def get_queryset(self):
        return self.model.objects.all()[:9]


class MoreBoardGamesView(View):
    def get(self, request, *args, **kwargs):            
        bgs = list(BoardGame.objects.values())
        
        lower_border = kwargs["lower_border"]
        upper_border = lower_border + 3
        
        reached_max = True if upper_border >= len(bgs) else False

        bgs = bgs[lower_border:upper_border]
        return JsonResponse(data={"data": bgs, "reached_max": reached_max})

class MoreSearchedBoardGamesView(View):
    def get(self, request, *args, **kwargs):
        max_searched_bgs = request.session.get("max_searched_bgs")
        searched_val = request.session.get("searched_val")
        bgs = list(BoardGame.objects.values().filter(name__contains=searched_val))

        lower_border = kwargs["lower_border"]
        upper_border = lower_border + 3

        reached_max = True if upper_border >= max_searched_bgs else False

        bgs = bgs[lower_border:upper_border]
        return JsonResponse(data={"data": bgs, "reached_max": reached_max})

class SearchForBGView(SuggestionFormMixin, CartMixin, View):
    def post(self, request, *args, **kwargs):
        super().post(request, *args, **kwargs)
        if request.POST.get("bg_name"):
            searched_bg = request.POST.get('bg_name')
            # В SQLite прикол в том что contains рааботает как регистронезависимая,
            # но на русские буквы это не расспространяется
            qs = BoardGame.objects.filter(name__contains=searched_bg)

            max_searched_bgs = len(qs)

            request.session["max_searched_bgs"] = max_searched_bgs
            request.session["searched_val"] = searched_bg

            context = {
                'boardgames': qs[:9],
                'cart': self.cart,
                'form': SuggestionFormMixin.form_class(),
                'max_bgs': max_searched_bgs
            }
            return render(request, "home.html", context=context)

class DownloadCSVView(View):
    def get(self, request, *args, **kwargs):
        bg_qs = BoardGame.objects.get_queryset_with_url()

        with open("bg_catalog.csv", 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ["Название на русском", "Название на английском", "Количество на складе", "Цена", "Ссылка"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for bg in bg_qs:
                writer.writerow({"Название на русском": bg.get('name'), "Название на английском": bg.get('eng_name'),
                                "Количество на складе": bg.get('quantity'), "Цена": bg.get('price'), "Ссылка": 'http://127.0.0.1:8000' + bg.get('url')})
                    
        with open("bg_catalog.csv", 'r', newline='', encoding='utf-8') as csvfile:
            response = HttpResponse(csvfile, content_type="text/csv")
            response['Content-Disposition'] = 'attachment; filename="bg_catalog.csv"' 

        os.remove('bg_catalog.csv')
        return response

class DownloadPDFView(View):
    
    def get(self, request, *args, **kwargs):
        pdfmetrics.registerFont(TTFont('CustomFont', Path(str(settings.PROJECT_ROOT) + "/static/boardgames/fonts/Vera.ttf")))
        custom_p_style = ParagraphStyle('Custom_p_style', fontName='CustomFont', fontSize=11)

        qs = BoardGame.objects.get_queryset_with_url()
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(buffer, rightMargin=0, leftMargin=0, topMargin=0, bottomMargin=0)
        
        elements = []
        data = [
            [
            Paragraph(bg.get('name'), custom_p_style),
            bg.get('quantity'),
            bg.get('price'),
            'http://127.0.0.1:8000' + bg.get('url') 
            ] 
            for bg in qs ]
        data.insert(0, [
            Paragraph("Название на русском", custom_p_style),
            Paragraph("Количество на складе", custom_p_style),
            "Цена",
            "Ссылка"
            ])

        t=Table(data, colWidths=[150, 55, 60, 300], rowHeights=55, splitByRow=True)
        t.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.pink),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
                ('FONT', (0, 0), (-1, -1), 'CustomFont', 11)
            ])
        )
        elements.append(t)
        doc.build(elements)
        
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename='bg_catalog.pdf')

class BoardGamesDetailView(CartMixin, SuggestionFormMixin, DetailView):

    model = BoardGame
    context_object_name = "boardgame"
    template_name = "boardgames/one_bg.html"
    slug_url_kwarg = "slug"
    slug_field = "slug"

    def get_queryset(self):
        return super().get_queryset().filter(slug__exact=self.kwargs.get("slug"))


class CartView(CartMixin, SuggestionFormMixin, View):

    def get(self, request, *args, **kwargs):
        context = {
            "cart": self.cart,
            "form": self.get_form()
        }
        return render(request, "boardgames/cart.html", context)


class AddToCartView(CartMixin, View):

    def get(self, request, *args, **kwargs):
        bg_slug = kwargs["slug"]
        bg = BoardGame.objects.get(slug=bg_slug)

        if bg in [product.boardgame for product in self.cart.products.all()]:
            cart_product = self.cart.products.filter(boardgame=bg)[0]
            cart_product.qty += 1
            cart_product.save()
        else:
            cart_product = CartProduct.objects.create(boardgame=bg)
            self.cart.products.add(cart_product)

        self.cart.save()
        messages.add_message(request, messages.INFO,
                             f"Товар \"{bg.name}\" был добавлен в корзину")
        return HttpResponseRedirect(reverse_lazy('boardgames:one_bg', kwargs={"slug": self.kwargs.get("slug")}))


class RemoveFromCartView(CartMixin, View):

    def get(self, request, *args, **kwargs):
        bg_slug = kwargs["slug"]
        bg = BoardGame.objects.get(slug=bg_slug)

        cart_product = self.cart.products.filter(boardgame=bg)[0]
        self.cart.products.remove(cart_product)
        cart_product.delete()

        self.cart.save()
        messages.add_message(request, messages.INFO,
                             f"Товар \"{bg.name}\" был удалён из корзины")
        return HttpResponseRedirect(reverse_lazy('boardgames:cart'))


class UpdateCartView(CartMixin, View):
    def post(self, request, *args, **kwargs):
        old_data = [[item.boardgame.name, item.qty]
                    for item in self.cart.products.all()]
        for old_val, new_val in zip(old_data, request.POST.items()):
            # Думаю оно будет правильно работать, т.к. zip идет до самой малой по длине из последовательностей

            old_name = old_val[0]
            new_name = new_val[0]
            
            old_qty = old_val[1]
            new_qty = int(new_val[1])

            if old_name == new_name and old_qty != new_qty:
                bg = BoardGame.objects.get(name=old_name)
                if new_qty <= bg.quantity:
                    cart_product = self.cart.products.filter(boardgame=bg).first()
                    cart_product.qty = new_qty
                    cart_product.save()
                    messages.add_message(request, messages.INFO,
                             f"Количество для игры \"{bg.name}\" обновлено успешно")
                else:
                    messages.add_message(request, messages.WARNING,
                             f"Запрашиваемое количество для игры \"{bg.name}\" больше, чем имеется на складе (максимум-{bg.quantity})")                   
            self.cart.save()
        # Сделать проверку на правильность выполненности view

        # Для случая, когда все хорошо
        response = {
            'status': 1,
            'message': 'Всё хорошо',
            'url': str(reverse_lazy('boardgames:cart'))
        }

        return HttpResponse(json.dumps(response), content_type='application/json')

class SetOrderView(CartMixin, View):
    def get (self, request, *args, **kwargs):
        self.cart.in_order = True
        order = Order.objects.create(cart=self.cart)
        self.cart.save()
        messages.add_message(request, messages.INFO,
                             f"Ваш заказ оформлен и добавлен в список заказов")
        return HttpResponseRedirect(reverse_lazy('boardgames:cart'))

class ListOrderView(SuggestionFormMixin, CartMixin, View):
    def get(self, request, *args, **kwargs):
        qs = Order.objects.filter(cart__owner__user=request.user)
        data = {
            "orders": qs,
            "form": self.get_form(),
            "cart": self.cart
        }
        return render(request, "boardgames/orders_list.html", context=data)


class BggHot15View(CartMixin, SuggestionFormMixin, View):
    def get(self, request, *args, **kwargs):
        bgg = BGGClient()
        lst = bgg.hot_items("boardgame")
        lst = lst[:25]

        all_db_bg = BoardGame.objects.get_queryset_with_url()
        all_db_bg_titles = [bg.get("eng_name").lower() for bg in all_db_bg]
        all_db_bg = [{bg.get("eng_name").lower(): bg.get(
            "url"), "ru_name": bg.get("name")} for bg in all_db_bg]

        context = {
            "cart": self.cart,
            "form": self.get_form(),
            "hot25lst": lst[:15],
            "all_db_bg": all_db_bg,
            "all_db_bg_titles": all_db_bg_titles
        }
        return render(request, "boardgames/bgghot15.html", context)
