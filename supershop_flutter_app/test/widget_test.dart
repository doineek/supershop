import 'package:flutter_test/flutter_test.dart';
import 'package:supershop_app/main.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const SupershopApp());
    expect(find.byType(SupershopApp), findsOneWidget);
  });
}
